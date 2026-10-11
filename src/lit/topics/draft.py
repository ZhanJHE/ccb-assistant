"""The draft skeleton: the shape of the paper, with every claim already anchored.

A topic still has to be written, and this module does not write it. What it produces
is the structure a paper of this kind needs, the questions each section has to answer,
and — attached to each section — the evidence that section may cite. Nothing else.
Prose composed anywhere else in the tool would be unanchored; here every claim either
points at a stored work with a page, or is visibly marked as still to be determined.

The section order follows how such a paper is actually argued, including the
four-step gap derivation the literature recommends: state what prior work achieved,
state what it could not do, introduce the move, then state the expected value.

Two sections deserve a note:

* **Expected experiments and datasets** is filled from what the corpus itself mentions.
  Dataset, benchmark and baseline names are extracted as *observations* — this is what
  neighbouring work uses, not a recommendation, and it is reported with its counts.
* **Anticipated criticism** writes the three hardest reviewer questions as prompts,
  because a topic that cannot answer them is a topic that should be dropped rather
  than written up.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ..core.util import short_hash, utc_now
from . import candidates as candidates_mod
from .ccf import CcfCatalog, default_catalog
from .store import save_json

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..library.store import Library

# How many stored works to consult when harvesting dataset and baseline names.
_MENTION_SCAN_LIMIT = 60
_MAX_REFERENCES = 20

_DATASET_PATTERNS = (
    re.compile(
        r"\b(?:on|using|with|over)\s+the\s+([A-Za-z][\w.+:\-]{2,28})\s+"
        r"(?:dataset|benchmark|corpus|suite|set)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b([A-Za-z][\w.+:\-]{2,28})\s+(?:dataset|benchmark|corpus|suite)\b"
    ),
)

_BASELINE_PATTERNS = (
    re.compile(
        r"\b(?:compared?|comparison)\s+(?:with|to|against)\s+"
        r"([A-Za-z][\w.+:\-]{2,28})",
        re.IGNORECASE,
    ),
    re.compile(r"\bbaselines?\s+(?:such as|including|like)\s+([A-Za-z][\w.+:\-]{2,28})", re.IGNORECASE),
    re.compile(r"\boutperforms?\s+([A-Za-z][\w.+:\-]{2,28})", re.IGNORECASE),
)

_MENTION_STOPWORDS = frozenset(
    """
    the this that these those our their its a an and or of for with using on in to
    method model approach framework results table figure section paper work
    standard large small real synthetic new same other such baseline dataset data
    """.split()
)


def _harvest(works: list[Any], patterns: tuple[re.Pattern[str], ...]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for work in works:
        text = f"{work.title() or ''} {work.abstract() or ''}"
        for pattern in patterns:
            for match in pattern.findall(text):
                name = match.strip().strip(".,;:")
                if not name or name.casefold() in _MENTION_STOPWORDS:
                    continue
                if len(name) < 3:
                    continue
                counts[name] = counts.get(name, 0) + 1
    rows = [{"name": name, "mentions": n} for name, n in counts.items()]
    rows.sort(key=lambda r: (-r["mentions"], r["name"].casefold()))
    return rows[:12]


def _reference_rows(
    library: "Library",
    work_ids: list[str],
    catalog: CcfCatalog,
) -> list[dict[str, Any]]:
    from ..library.cite import to_bibtex

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for work_id in work_ids:
        if not work_id or work_id in seen:
            continue
        seen.add(work_id)
        work = library.load(work_id)
        if work is None:
            continue
        venue = work.venue() or ""
        match = catalog.match(venue) if venue else None
        try:
            bibtex = to_bibtex(work)
        except Exception:
            bibtex = ""
        rows.append(
            {
                "work_id": work.work_id,
                "title": work.title(),
                "authors": work.authors(),
                "year": work.year(),
                "venue": venue,
                "ccf": match.rank if match else "",
                "bibtex": bibtex,
            }
        )
        if len(rows) >= _MAX_REFERENCES:
            break
    return rows


def _anchor_for(evidence: dict[str, Any]) -> dict[str, Any]:
    """The citation anchor a section may quote, or an explicit statement of absence."""
    if evidence.get("type") == "declared_gap":
        return {
            "kind": "quotation",
            "work_id": evidence.get("work_id", ""),
            "page": evidence.get("page"),
            "sentence": evidence.get("sentence", ""),
        }
    return {
        "kind": "statistic",
        "terms": list(evidence.get("terms") or []),
        "together": evidence.get("together"),
        "expected": evidence.get("expected"),
        "deficit": evidence.get("deficit"),
    }


def _sections(
    candidate: dict[str, Any],
    *,
    references: list[dict[str, Any]],
    datasets: list[dict[str, Any]],
    baselines: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    operator = candidate.get("operator") or {}
    evidence = candidate.get("evidence") or {}
    problem = candidate.get("problem", "")
    anchor = _anchor_for(evidence)

    citation_ids = [row["work_id"] for row in references]
    support_ids = citation_ids[:6] or ["<no stored work supports this yet>"]
    coverage_ids = [row["work_id"] for row in coverage] or ["<none found>"]

    return [
        {
            "n": 1,
            "heading": "Background and problem",
            "purpose": "Establish why the problem matters before naming any gap.",
            "write": [
                "What is the task, in one sentence a non-specialist would follow?",
                "Who relies on it, and what breaks when it is done badly?",
                "What is the current state of the art in this direction, by name?",
            ],
            "anchors": [anchor],
            "must_cite": support_ids,
        },
        {
            "n": 2,
            "heading": "Related work and the gap",
            "purpose": (
                "The four-step derivation: what prior work achieved, what it could not "
                "do, what this topic does instead, and why that is worth doing."
            ),
            "write": [
                "Step 1 — what exactly did prior work establish? (cite, do not summarise "
                "from memory)",
                "Step 2 — what did it explicitly not do? Quote the source sentence.",
                "Step 3 — what does this topic do instead?",
                "Step 4 — what is the expected value if it works?",
            ],
            "anchors": [anchor],
            "must_cite": support_ids,
            "evidence_to_quote": (
                [anchor] if anchor.get("kind") == "quotation" else []
            ),
            "gap_kind": evidence.get("kind", ""),
            "marker_found": evidence.get("marker", ""),
        },
        {
            "n": 3,
            "heading": "Research questions and hypotheses",
            "purpose": "Turn the opening into falsifiable questions.",
            "write": [
                problem,
                "State the hypothesis so that a negative result is possible.",
                "State the one-sentence claim: what did we do that nobody has done? If it "
                "takes more than one sentence, the topic is still too broad.",
            ],
            "anchors": [anchor],
            "must_cite": [],
        },
        {
            "n": 4,
            "heading": "Contributions",
            "purpose": "One line per contribution, each traceable to a section that delivers it.",
            "write": [
                f"Contribution 1 — the operator applied here is "
                f"'{operator.get('name', '')}' ({operator.get('novelty_type', '')}, "
                f"difficulty {operator.get('difficulty', '?')}/5).",
                "Contribution 2 — the empirical result that supports it.",
                "Contribution 3 — the artefact, benchmark or analysis others can reuse.",
            ],
            "anchors": [anchor],
            "must_cite": [],
            "novelty_type": operator.get("novelty_type", ""),
            "difficulty": operator.get("difficulty"),
        },
        {
            "n": 5,
            "heading": "Technical approach",
            "purpose": "How the method works, at the level of an architecture diagram plus prose.",
            "write": [
                f"The move: {operator.get('move', '')}",
                "What is reused unchanged, and what is new?",
                "What is the one mechanism the paper is really about?",
            ],
            "anchors": [anchor],
            "must_cite": [],
        },
        {
            "n": 6,
            "heading": "Expected experiments and datasets",
            "purpose": (
                "The evaluation plan. Dataset and baseline names below are what "
                "neighbouring work in this direction actually uses — observed mentions "
                "with their counts, not recommendations."
            ),
            "write": [
                "Which dataset actually fits the question, and is it obtainable?",
                "Which baselines must be run for the claim to be credible?",
                "Which metrics can falsify the hypothesis?",
                "Which ablations isolate the mechanism?",
            ],
            "anchors": [anchor],
            "must_cite": [],
            "observed_datasets": datasets,
            "observed_baselines": baselines,
            "note": (
                "A name appearing here means the corpus mentions it, nothing more. "
                "Verify licence, size and availability before committing to it."
            ),
        },
        {
            "n": 7,
            "heading": "Expected contributions and anticipated criticism",
            "purpose": (
                "Write the three hardest reviewer questions now. A topic that cannot "
                "answer them should be dropped rather than written up."
            ),
            "write": [
                "Q1 — 'This is just A plus B; what is the new mechanism?'",
                "Q2 — 'The gap is not real; paper X already did this.' Which stored work "
                "is the strongest counter-evidence? Read it first.",
                "Q3 — 'The evaluation does not support the claim.' Which result would "
                "change your mind?",
            ],
            "anchors": [anchor],
            "must_cite": [],
            "counter_evidence_to_read": coverage_ids,
        },
        {
            "n": 8,
            "heading": "References",
            "purpose": "Only works the library actually holds. Do not invent an entry.",
            "write": [
                "Cite every claim about prior work from this list.",
                "If a needed reference is missing, run `lit find` and `lit get` rather "
                "than typing it from memory.",
            ],
            "anchors": [],
            "must_cite": citation_ids,
        },
        {
            "n": 9,
            "heading": "Evidence appendix",
            "purpose": (
                "Every quotation this topic rests on, with work_id and page, so a reader "
                "can check the gap claim without re-running the survey."
            ),
            "write": ["Paste the anchors as found; do not paraphrase them."],
            "anchors": [anchor],
            "must_cite": citation_ids,
        },
    ]


def draft(
    library: "Library",
    candidate: dict[str, Any] | str,
    *,
    catalog: CcfCatalog | None = None,
    store: bool = True,
) -> dict[str, Any]:
    """Build the section skeleton for one candidate, with its evidence attached."""
    catalog = catalog or default_catalog()
    stored_set: dict[str, Any] | None = None
    if isinstance(candidate, str):
        found = candidates_mod.find_candidate(library, candidate)
        if found is None:
            return {
                "error": "unknown_candidate",
                "candidate_id": candidate,
                "message": (
                    "No stored candidate with that id. Run "
                    "`lit topics candidates <survey_id>` first; candidate ids come from "
                    "that output."
                ),
            }
        candidate, stored_set = found

    survey_id = str(candidate.get("survey_id") or "")
    survey = None
    if stored_set is not None:
        survey = stored_set.get("survey")
    if survey is None and survey_id:
        from .survey import load_survey

        survey = load_survey(library, survey_id)
    survey = survey or {}

    works: list[Any] = []
    for row in (survey.get("works") or [])[:_MENTION_SCAN_LIMIT]:
        work = library.load(str(row.get("work_id") or ""))
        if work is not None:
            works.append(work)

    coverage = list((candidate.get("local_coverage") or {}).get("works") or [])
    evidence = candidate.get("evidence") or {}
    citation_ids = []
    if evidence.get("work_id"):
        citation_ids.append(str(evidence["work_id"]))
    citation_ids.extend(str(row.get("work_id") or "") for row in coverage)
    citation_ids.extend(str(row.get("work_id") or "") for row in (survey.get("works") or [])[:8])

    references = _reference_rows(library, citation_ids, catalog)

    candidate_id = str(candidate.get("candidate_id") or "")
    topic_id = short_hash("topic", candidate_id)

    record: dict[str, Any] = {
        "topic_id": topic_id,
        "candidate_id": candidate_id,
        "survey_id": survey_id,
        "query": candidate.get("query", ""),
        "title_hint": candidate.get("title_hint", ""),
        "status": "draft",
        "created_at": utc_now(),
        "operator": candidate.get("operator") or {},
        "evidence": evidence,
        "problem": candidate.get("problem", ""),
        "score": candidate.get("score"),
        "score_basis": candidate.get("score_basis") or [],
        "context": {
            "directness": float(
                candidate.get("directness")
                if candidate.get("directness") is not None
                else (1.0 if evidence.get("type") == "declared_gap" else 0.5)
            ),
            "support": int(candidate.get("support") or 0),
            "corpus_works": int((survey.get("corpus") or {}).get("works") or 0),
            "local_coverage_hits": int(
                (candidate.get("local_coverage") or {}).get("hits") or 0
            ),
        },
        "dedup_keys": [str(candidate.get("dedup_key") or "")],
        "sections": _sections(
            candidate,
            references=references,
            datasets=_harvest(works, _DATASET_PATTERNS),
            baselines=_harvest(works, _BASELINE_PATTERNS),
            coverage=coverage,
        ),
        "references": references,
        "corpus": {
            "works": int((survey.get("corpus") or {}).get("works") or 0),
            "with_fulltext": int((survey.get("corpus") or {}).get("with_fulltext") or 0),
        },
        "next_steps": [
            "Write each section from the anchors attached to it; do not introduce a "
            "claim without one.",
            "Run `lit topics rate <topic_id>` for the CCF estimate and its reasoning.",
            "Run `lit topics save <topic_id>` to store the record and export the "
            "Markdown draft.",
        ],
    }
    if store:
        save_json(library, "records", topic_id, record)
        library.log("topics_topic_drafted", {"topic_id": topic_id, "candidate_id": candidate_id})
    return record


def render_markdown(record: dict[str, Any]) -> str:
    """The Markdown draft: the skeleton, its anchors, and its references."""
    lines: list[str] = []
    operator = record.get("operator") or {}
    evidence = record.get("evidence") or {}
    rating = record.get("rating") or {}

    title = record.get("title_hint") or record.get("query") or "Untitled topic"
    lines.append(f"# {title}")
    lines.append("")
    lines.append("<!-- Generated by `lit topics`. The prose is written by the agent; "
                 "every claim below carries the anchor it must be built from. -->")
    lines.append("")
    lines.append("| | |")
    lines.append("|---|---|")
    lines.append(f"| topic_id | `{record.get('topic_id', '')}` |")
    lines.append(f"| direction | {record.get('query', '')} |")
    lines.append(f"| operator | {operator.get('name', '')} "
                 f"({operator.get('novelty_type', '')}, "
                 f"difficulty {operator.get('difficulty', '?')}/5) |")
    if rating:
        lines.append(f"| estimated CCF | **{rating.get('estimated_ccf', '?')}** "
                     f"(upper bound {rating.get('upper_bound', '?')}, "
                     f"confidence {rating.get('confidence', '?')}) |")
    lines.append("")

    if rating:
        lines.append("## Rating basis")
        lines.append("")
        for item in rating.get("basis") or []:
            lines.append(f"- **{item.get('rule')}** = `{item.get('value')}` — "
                         f"{item.get('why')}")
        if rating.get("risks"):
            lines.append("")
            lines.append("Risks:")
            for risk in rating["risks"]:
                lines.append(f"- {risk}")
        lines.append("")
        lines.append(f"> {rating.get('disclaimer', '')}")
        lines.append("")

    for section in record.get("sections") or []:
        lines.append(f"## {section.get('n')}. {section.get('heading')}")
        lines.append("")
        if section.get("purpose"):
            lines.append(f"*{section['purpose']}*")
            lines.append("")
        for item in section.get("write") or []:
            lines.append(f"- [ ] {item}")
        anchors = section.get("anchors") or []
        quotes = [a for a in anchors if a.get("kind") == "quotation"]
        stats = [a for a in anchors if a.get("kind") == "statistic"]
        if quotes:
            lines.append("")
            lines.append("Evidence to quote:")
            for anchor in quotes:
                page = anchor.get("page")
                where = f"p.{page}" if page is not None else "abstract"
                lines.append(f"> [{anchor.get('work_id')} {where}] "
                             f"{anchor.get('sentence')}")
        for stat in stats:
            lines.append("")
            lines.append(
                f"Evidence (statistic): `{' + '.join(stat.get('terms') or [])}` appear "
                f"together in {stat.get('together')} works against "
                f"{stat.get('expected')} expected (deficit {stat.get('deficit')})."
            )
        if section.get("observed_datasets"):
            lines.append("")
            lines.append("Datasets mentioned by neighbouring work: "
                         + ", ".join(
                             f"{d['name']} ({d['mentions']})"
                             for d in section["observed_datasets"]
                         ))
        if section.get("observed_baselines"):
            lines.append("")
            lines.append("Baselines mentioned by neighbouring work: "
                         + ", ".join(
                             f"{b['name']} ({b['mentions']})"
                             for b in section["observed_baselines"]
                         ))
        if section.get("must_cite"):
            lines.append("")
            lines.append("Must cite: " + ", ".join(
                f"`{wid}`" for wid in section["must_cite"]
            ))
        lines.append("")

    lines.append("## References")
    lines.append("")
    references = record.get("references") or []
    if not references:
        lines.append("_The library holds no work that supports this topic yet._")
    for ref in references:
        ccf = f" (CCF-{ref['ccf']})" if ref.get("ccf") else ""
        lines.append(f"- `{ref['work_id']}` — {ref.get('title', '')}"
                     f"{ccf}")
    lines.append("")
    lines.append("## BibTeX")
    lines.append("")
    lines.append("```bibtex")
    for ref in references:
        if ref.get("bibtex"):
            lines.append(ref["bibtex"].strip())
            lines.append("")
    lines.append("```")

    if evidence.get("sentence"):
        lines.append("")
        lines.append("## Core evidence")
        lines.append("")
        page = evidence.get("page")
        where = f"p.{page}" if page is not None else "abstract"
        lines.append(f"> [{evidence.get('work_id')} {where}] {evidence['sentence']}")
        lines.append("")
        lines.append(f"declared gap kind: `{evidence.get('kind', '')}` "
                     f"(marker: `{evidence.get('marker', '')}`)")
    return "\n".join(lines) + "\n"
