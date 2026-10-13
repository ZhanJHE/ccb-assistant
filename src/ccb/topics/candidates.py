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

from ..core.util import short_hash
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
    # The sentence is part of the key. Two limitations stated on the same page of the same
    # paper are two different gaps; hashing only (kind, work_id, page) gave them one key,
    # hence one candidate id, hence one topic_id — so the second `topics draft` silently
    # overwrote the first record while its dedup key stayed retired.
    sentence = short_hash(str(evidence.get("sentence", "")).strip().casefold(), length=10)
    return "gap::" + short_hash(
        str(evidence.get("kind", "")),
        str(evidence.get("work_id", "")),
        str(evidence.get("page", "")),
        sentence,
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
    novelty_hits: int | None,
    corpus_size: int,
) -> tuple[float, list[dict[str, Any]]]:
    """Four weighted parts, each normalised against the corpus so it can vary.

    Everything is divided by the size of the direction's corpus. Normalising against a
    fixed target instead would saturate every part on a small corpus and produce a
    column of identical scores, which is exactly the situation in which a ranking stops
    carrying information.

    ``novelty_hits=None`` means "not measured" (the self-check was skipped, or the
    evidence yielded no usable terms). The part is then dropped and its weight is
    redistributed over the others, and the basis says so — reporting a measured zero
    instead would assert "0 of N works share these terms" about a question nobody asked.
    """
    scale = max(corpus_size, 1)
    support_part = min(support / scale, 1.0)
    ambition = (difficulty - operators_mod._MIN_DIFFICULTY) / (
        operators_mod._MAX_DIFFICULTY - operators_mod._MIN_DIFFICULTY
    )
    measured = novelty_hits is not None
    base = (
        WEIGHTS["directness"] * directness
        + WEIGHTS["support"] * support_part
        + WEIGHTS["ambition"] * ambition
    )
    if measured:
        novelty = 1.0 - min(int(novelty_hits) / scale, 1.0)
        total = base + WEIGHTS["novelty"] * novelty
        novelty_value: float | None = round(novelty, 3)
        novelty_why = (
            f"{novelty_hits} of {corpus_size} works in this direction share this "
            "candidate's terms"
        )
    else:
        remainder = sum(WEIGHTS.values()) - WEIGHTS["novelty"]
        total = base / remainder if remainder > 0 else base
        novelty_value = None
        novelty_why = (
            "not measured, so this part's weight was redistributed over the others"
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
            "value": novelty_value,
            "weight": WEIGHTS["novelty"],
            "why": novelty_why,
        },
    ]
    return round(total, 4), basis


def _direction_corpus(library: "Library", survey: dict[str, Any]) -> list[tuple[str, str]]:
    """(work_id, searchable text) for the direction's works, loaded once per run.

    Loaded once because the alternative — a library query per candidate term — is what
    made the coverage number come from a different population than the one the score
    divides by.
    """
    out: list[tuple[str, str]] = []
    for entry in survey.get("works") or []:
        # `survey["works"]` is a list of summary rows (the shape the survey payload
        # publishes), but a caller may hand over plain ids; accept both rather than
        # silently measuring an empty direction.
        wid = str(entry.get("work_id") if isinstance(entry, dict) else entry or "")
        if not wid:
            continue
        w = library.load(wid)
        if w is None:
            continue
        haystack = (
            w.title() + " " + w.abstract() + " " + str(w.extras.get("user_note", ""))
        ).casefold()
        out.append((w.work_id, haystack))
    return out


def _local_coverage(
    library: "Library",
    candidate_terms: Iterable[str],
    *,
    corpus: list[tuple[str, str]] | None = None,
    display: int = 5,
    search_limit: int = 50,
) -> dict[str, Any]:
    """Stored works that share the candidate's terms, in two explicitly separate scopes.

    * ``hits`` / ``of`` — works **in this direction** that share a term. This is the
      number the novelty part divides by the direction's corpus size, so numerator and
      denominator describe the same population.
    * ``library_hits`` / ``works`` — the whole-library reading list ("read these before
      claiming the combination is new"). It is informational and deliberately not used
      for scoring: it is capped by the search limit, so treating it as a count both mixed
      two populations and silently zeroed novelty for every candidate in a library much
      larger than the direction.
    """
    terms = [str(t).strip().casefold() for t in list(candidate_terms)[:4] if str(t).strip()]
    if not terms:
        return {
            "checked": False,
            "hits": 0,
            "of": len(corpus or []),
            "scope": "direction",
            "library_hits": 0,
            "works": [],
            "note": (
                "no candidate terms could be extracted, so local coverage was not "
                "measured (the extractor handles Latin-script terms only)"
            ),
        }

    direction_hits = 0
    if corpus is not None:
        matched: set[str] = set()
        for wid, haystack in corpus:
            if wid in matched:
                continue
            if any(term in haystack for term in terms):
                matched.add(wid)
        direction_hits = len(matched)

    seen: dict[str, dict[str, Any]] = {}
    for term in terms:
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
    return {
        "checked": True,
        "hits": direction_hits,
        "of": len(corpus or []),
        "scope": "direction",
        "library_hits": len(rows),
        "works": rows[:display],
    }


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
                    "No stored survey with that id. Run `ccb topics survey \"<direction>\"` "
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
    seen_keys: set[str] = set()

    raw = _build_raw(survey, gap_result, per_kind=per_kind, total_works=total_works)
    ranked: list[dict[str, Any]] = []
    for item in raw:
        op = item["operator"]
        key = _evidence_key(item["evidence"])
        dedup_key = f"{op.id}::{key}"
        if dedup_key in known or dedup_key in seen_keys:
            # `known` is history (already committed); `seen_keys` is this run. Without the
            # second, two rows could carry one id, and one `topics draft` would overwrite
            # the other's record.
            continue
        seen_keys.add(dedup_key)
        score, basis = _score(
            directness=item["directness"],
            support=item["support"],
            difficulty=op.difficulty,
            # Not measured yet: this pass only orders the shortlist, and every candidate
            # gets the same (dropped) novelty part, so the ordering is unaffected.
            novelty_hits=None,
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
    direction = _direction_corpus(library, survey) if self_check else None
    candidates: list[dict[str, Any]] = []
    for row in shortlist:
        op = row["_op"]
        coverage = (
            _local_coverage(library, _candidate_terms(row["_evidence"]), corpus=direction)
            if self_check
            else {
                "checked": False,
                "hits": 0,
                "of": total_works,
                "scope": "direction",
                "library_hits": 0,
                "works": [],
                "note": (
                    "--no-self-check: local coverage was not measured, so the novelty "
                    "part is omitted rather than reported as zero"
                ),
            }
        )
        score, basis = _score(
            directness=row["_directness"],
            support=row["_support"],
            difficulty=op.difficulty,
            novelty_hits=coverage["hits"] if coverage.get("checked") else None,
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
                "score_scope": "measured" if coverage.get("checked") else "no-self-check",
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
            "combination has already been mined (`ccb topics list`). "
            + (
                "Every candidate was filtered as already mined."
                if raw
                else "Run `ccb topics gaps <survey_id>` to see what evidence exists."
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
