"""Turning gap evidence into ranked topic candidates.

A candidate is one (evidence, operator) pair: a specific gap the corpus documents,
read through a specific way of making a contribution. Generating them is mechanical;
ranking them is where the module has to stay honest.

Three things are decided here:

* **What supports the candidate.** A candidate inherits its evidence, and the evidence
  is always quotable — a sentence with a work_id and a page, or a term pair with its
  counts. There is no candidate without an anchor.
* **How it is scored.** Four weighted parts, each reported with its value and its
  reason: how *directly* the evidence states a gap (an author's own sentence beats a
  co-occurrence statistic), how much of the corpus *supports* it, how *ambitious* the
  operator is, and how *novel* the combination looks against what the library already
  holds. The score orders a reading list; it is not a prediction.
* **What has already been mined.** Each candidate carries a stable de-duplication key.
  A key consumed by a committed topic is filtered out, which is what makes "one at a
  time" mean anything over repeated runs.

Scoring never fabricates a novelty verdict: local coverage is reported as a count of
works that share the candidate's terms, and the candidate is told to treat that as
evidence to be read, not as a rejection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

from ..core.util import normalize_text, short_hash
from . import gaps as gaps_mod
from . import operators as operators_mod
from . import terms as terms_mod
from .ccf import CcfCatalog, default_catalog
from .store import mined_keys

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..library.store import Library

# Weights sum to 1.0. Kept explicit so a score can be recomputed by hand.
WEIGHTS = {
    "directness": 0.35,
    "support": 0.25,
    "ambition": 0.20,
    "novelty": 0.20,
}

# How many candidates survive to the (more expensive) novelty self-check.
SELF_CHECK_FACTOR = 3


def _fill(template: str, values: dict[str, Any]) -> str:
    """Substitute placeholders, leaving unknown ones visible rather than empty."""
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def _evidence_key(evidence: dict[str, Any]) -> str:
    if evidence["type"] == "sparse_pair":
        a, b = sorted(evidence["terms"])
        return f"pair::{a}::{b}"
    return "gap::" + short_hash(
        str(evidence.get("kind", "")),
        str(evidence.get("work_id", "")),
        str(evidence.get("page", "")),
    )


def _pair_values(pair: dict[str, Any], total: int) -> dict[str, Any]:
    a, b = pair["terms"]
    return {
        "a": a,
        "b": b,
        "together": pair["together"],
        "expected": pair["expected"],
        "total": total,
    }


def _gap_values(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": row["kind"].replace("_", " "),
        "subject": row.get("title", ""),
        "gap": row.get("sentence", ""),
        "year": row.get("year") or "",
    }


def _support_for_pair(pair: dict[str, Any]) -> int:
    return min(pair["docs_a"], pair["docs_b"])


def _score(
    *,
    directness: float,
    support: int,
    difficulty: int,
    novelty_hits: int,
    corpus_size: int,
) -> tuple[float, list[dict[str, Any]]]:
    """Four weighted parts, each normalised against the corpus so it can vary.

    Everything is divided by the size of the direction's corpus. Normalising against a
    fixed target instead would saturate every part on a small corpus and produce a
    column of identical scores, which is exactly the situation in which a ranking stops
    carrying information.
    """
    scale = max(corpus_size, 1)
    support_part = min(support / scale, 1.0)
    ambition = (difficulty - operators_mod._MIN_DIFFICULTY) / (
        operators_mod._MAX_DIFFICULTY - operators_mod._MIN_DIFFICULTY
    )
    novelty = 1.0 - min(novelty_hits / scale, 1.0)
    total = (
        WEIGHTS["directness"] * directness
        + WEIGHTS["support"] * support_part
        + WEIGHTS["ambition"] * ambition
        + WEIGHTS["novelty"] * novelty
    )
    basis = [
        {
            "part": "directness",
            "value": round(directness, 3),
            "weight": WEIGHTS["directness"],
            "why": (
                "the author states the gap in their own words"
                if directness >= 1.0
                else "the gap is inferred from what the corpus uses together"
            ),
        },
        {
            "part": "support",
            "value": round(support_part, 3),
            "weight": WEIGHTS["support"],
            "why": f"{support} of {corpus_size} works in the direction bear on this "
                   f"evidence",
        },
        {
            "part": "ambition",
            "value": round(ambition, 3),
            "weight": WEIGHTS["ambition"],
            "why": f"the operator is rated {difficulty}/5 in difficulty",
        },
        {
            "part": "novelty",
            "value": round(novelty, 3),
            "weight": WEIGHTS["novelty"],
            "why": f"{novelty_hits} of {corpus_size} stored works share this candidate's "
                   f"terms",
        },
    ]
    return round(total, 4), basis


def _local_coverage(
    library: "Library",
    candidate_terms: Iterable[str],
    *,
    display: int = 5,
    search_limit: int = 50,
) -> dict[str, Any]:
    """Stored works that share the candidate's terms, as a reading list, not a verdict.

    The count is the true number of matches; only the listing is trimmed. Trimming the
    count as well would silently cap the novelty part of the score.
    """
    seen: dict[str, dict[str, Any]] = {}
    for term in list(candidate_terms)[:4]:
        try:
            hits = library.search(term, limit=search_limit)
        except Exception:
            hits = []
        for hit in hits:
            wid = str(hit.get("work_id") or "")
            if wid and wid not in seen:
                seen[wid] = {
                    "work_id": wid,
                    "title": hit.get("title", ""),
                    "year": hit.get("year"),
                }
    rows = list(seen.values())
    rows.sort(key=lambda r: (-(r.get("year") or 0), r["work_id"]))
    return {"hits": len(rows), "works": rows[:display]}


def _candidate_terms(evidence: dict[str, Any]) -> list[str]:
    if evidence["type"] == "sparse_pair":
        return list(evidence["terms"])
    return sorted(terms_mod.extract_terms(evidence.get("sentence", ""), max_n=2))[:6]


def _build_raw(
    survey: dict[str, Any],
    gap_result: dict[str, Any],
    *,
    per_kind: int,
    total_works: int,
) -> list[dict[str, Any]]:
    raw: list[dict[str, Any]] = []

    pairs = list(gap_result.get("sparse_pairs") or [])[:per_kind]
    for pair in pairs:
        for op in operators_mod.for_evidence("sparse_pair"):
            evidence = {
                "type": "sparse_pair",
                "terms": list(pair["terms"]),
                "together": pair["together"],
                "expected": pair["expected"],
                "deficit": pair["deficit"],
                "docs_a": pair["docs_a"],
                "docs_b": pair["docs_b"],
                "anchor": {
                    "kind": "co-occurrence statistic over the stored corpus",
                    "works_total": total_works,
                },
            }
            problem = _fill(op.problem, _pair_values(pair, total_works))
            raw.append(
                {
                    "operator": op,
                    "evidence": evidence,
                    "problem": problem,
                    "directness": 0.5,
                    "support": _support_for_pair(pair),
                }
            )

    by_kind: dict[str, list[dict[str, Any]]] = {}
    for row in gap_result.get("declared_gaps") or []:
        by_kind.setdefault(str(row.get("kind")), []).append(row)

    for kind, rows in sorted(by_kind.items()):
        # Support is how many *works* acknowledge this kind of gap, not how many
        # sentences were extracted — one verbose paper must not look like a field.
        kind_support = len({str(other.get("work_id")) for other in rows})
        for row in rows[:per_kind]:
            for op in operators_mod.for_evidence(kind):
                evidence = {
                    "type": "declared_gap",
                    "kind": kind,
                    "marker": row.get("marker", ""),
                    "sentence": row.get("sentence", ""),
                    "work_id": row.get("work_id", ""),
                    "title": row.get("title", ""),
                    "year": row.get("year"),
                    "page": row.get("page"),
                    "anchor": {
                        "work_id": row.get("work_id", ""),
                        "page": row.get("page"),
                        "title": row.get("title", ""),
                    },
                }
                problem = _fill(op.problem, _gap_values(row))
                raw.append(
                    {
                        "operator": op,
                        "evidence": evidence,
                        "problem": problem,
                        "directness": 1.0,
                        "support": kind_support,
                    }
                )
    return raw


def build(
    library: "Library",
    survey: dict[str, Any] | str,
    *,
    gap_result: dict[str, Any] | None = None,
    limit: int = 25,
    per_kind: int = 15,
    include_mined: bool = False,
    self_check: bool = True,
    catalog: CcfCatalog | None = None,
) -> dict[str, Any]:
    """Generate and rank topic candidates for a survey's direction."""
    from .survey import load_survey

    if isinstance(survey, str):
        loaded = load_survey(library, survey)
        if loaded is None:
            return {
                "error": "unknown_survey",
                "survey_id": survey,
                "message": (
                    "No stored survey with that id. Run `lit topics survey \"<direction>\"` "
                    "first."
                ),
            }
        survey = loaded

    if gap_result is None:
        gap_result = gaps_mod.gaps(library, survey)
    if gap_result.get("error"):
        return {"error": gap_result["error"], "message": gap_result.get("message", "")}

    catalog = catalog or default_catalog()
    survey_id = str(survey.get("survey_id") or "")
    total_works = int((survey.get("corpus") or {}).get("works") or 0)
    known = set() if include_mined else mined_keys(library)
    already = mined_keys(library)

    raw = _build_raw(survey, gap_result, per_kind=per_kind, total_works=total_works)
    ranked: list[dict[str, Any]] = []
    for item in raw:
        op = item["operator"]
        key = _evidence_key(item["evidence"])
        dedup_key = f"{op.id}::{key}"
        if dedup_key in known:
            continue
        score, basis = _score(
            directness=item["directness"],
            support=item["support"],
            difficulty=op.difficulty,
            novelty_hits=0,
            corpus_size=total_works,
        )
        ranked.append(
            {
                "_op": op,
                "_evidence": item["evidence"],
                "_support": item["support"],
                "_directness": item["directness"],
                "_basis": basis,
                "_score": score,
                "_dedup_key": dedup_key,
                "_problem": item["problem"],
                "_already_mined": dedup_key in already,
            }
        )

    ranked.sort(key=lambda row: (-row["_score"], row["_dedup_key"]))

    # The novelty self-check costs a query per candidate, so only the shortlist gets it.
    shortlist = ranked[: max(limit * SELF_CHECK_FACTOR, limit)] if self_check else ranked[:limit]
    candidates: list[dict[str, Any]] = []
    for row in shortlist:
        op = row["_op"]
        coverage = (
            _local_coverage(library, _candidate_terms(row["_evidence"]))
            if self_check
            else {"hits": 0, "works": []}
        )
        score, basis = _score(
            directness=row["_directness"],
            support=row["_support"],
            difficulty=op.difficulty,
            novelty_hits=coverage["hits"],
            corpus_size=total_works,
        )
        candidate_id = short_hash(
            "candidate", survey_id, op.id, row["_dedup_key"]
        )
        candidates.append(
            {
                "candidate_id": candidate_id,
                "survey_id": survey_id,
                "query": survey.get("query", ""),
                "title_hint": _title_hint(row["_problem"], row["_evidence"]),
                "operator": {
                    "id": op.id,
                    "name": op.name,
                    "novelty_type": op.novelty_type,
                    "difficulty": op.difficulty,
                    "ccf_ceiling": op.ccf_ceiling,
                    "move": op.move,
                },
                "evidence": row["_evidence"],
                "problem": row["_problem"],
                "score": score,
                "score_basis": basis,
                "support": row["_support"],
                "directness": row["_directness"],
                "local_coverage": coverage,
                "dedup_key": row["_dedup_key"],
                "already_mined": row["_already_mined"],
            }
        )

    # Ties are broken by what makes one candidate easier to defend than another: a
    # more ambitious operator, then an author's own sentence over a statistic, then
    # the id so the order is stable across runs.
    candidates.sort(
        key=lambda c: (
            -c["score"],
            -c["operator"]["difficulty"],
            0 if c["evidence"]["type"] == "declared_gap" else 1,
            c["candidate_id"],
        )
    )
    kept = candidates[:limit]

    result: dict[str, Any] = {
        "survey_id": survey_id,
        "query": survey.get("query", ""),
        "generated": len(ranked),
        "returned": len(kept),
        "excluded_as_mined": len(raw) - len(ranked),
        "weights": WEIGHTS,
        "candidates": kept,
        # Embedded so a stored candidate set is self-contained: `topics draft` can
        # build references without depending on the survey still being on disk.
        "survey": {
            "survey_id": survey_id,
            "query": survey.get("query", ""),
            "corpus": survey.get("corpus") or {},
            "terms": survey.get("terms") or [],
            "works": survey.get("works") or [],
        },
        "note": (
            "Scores order a reading list; they are not acceptance predictions. "
            "`local_coverage` lists stored works that share this candidate's terms — "
            "read them before claiming the combination is unstudied."
        ),
    }
    if not kept:
        result["message"] = (
            "No candidates. Either the direction has no usable gap evidence, or every "
            "combination has already been mined (`lit topics list`). "
            + (
                "Every candidate was filtered as already mined."
                if raw
                else "Run `lit topics gaps <survey_id>` to see what evidence exists."
            )
        )
    return result


def _title_hint(problem: str, evidence: dict[str, Any]) -> str:
    """A short, structural label for a candidate — not a finished title.

    It names the work the gap came from and what kind of shortfall it describes, so a
    reader can tell two candidates apart at a glance. The real title is the agent's.
    """
    if evidence["type"] == "sparse_pair":
        a, b = evidence["terms"]
        return f"{a} x {b} (uncombined)"
    kind = str(evidence.get("kind", "")).replace("_", " ")
    title = str(evidence.get("title", "")).strip()
    year = evidence.get("year")
    where = f"{title[:60]} ({year})" if year else title[:60]
    return f"{where} — {kind} opening" if where else f"{kind} opening"


def save_candidates(library: "Library", result: dict[str, Any]) -> str:
    from .store import save_json

    survey_id = str(result.get("survey_id") or "")
    if not survey_id:
        raise ValueError("candidate set has no survey_id")
    payload = dict(result)
    from ..core.util import utc_now

    payload.setdefault("created_at", utc_now())
    save_json(library, "candidates", survey_id, payload)
    return survey_id


def find_candidate(library: "Library", candidate_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Locate a candidate by id across the stored candidate sets."""
    from .store import list_json

    for stored in list_json(library, "candidates"):
        for candidate in stored.get("candidates", []):
            if candidate.get("candidate_id") == candidate_id:
                return candidate, stored
    return None
