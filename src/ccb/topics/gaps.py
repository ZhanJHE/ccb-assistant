"""Gap mining: the evidence a topic has to stand on.

Three kinds of evidence are collected, and all three are things the corpus actually
says rather than things the tool infers about it:

1. **Declared gaps.** Sentences in which an author states a limitation, an
   assumption, a cost, or a piece of future work. This is the strongest signal there
   is: an author writing "future work will explore X" has already named a topic, and
   the sentence is quotable evidence for it. Each hit carries its ``work_id`` and page.
2. **Sparse term pairs.** Two concepts the direction uses heavily but rarely together.
   This is the computable form of the "A + B" recombination move, and the arithmetic
   behind it is reported so it can be checked by hand.
3. **Gap-kind tallies.** Each declared gap is labelled with the kind of shortfall it
   describes — absence, limitation, breadth, inefficiency, idealisation, or future
   work — because the five kinds support very different topics.

Nothing here writes prose. Every entry is a quotation with an anchor, or a count with
its inputs, so a generated topic can be audited sentence by sentence.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Iterable

from . import terms as terms_mod
from .store import load_json

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..library.store import Library

# Ordered by how directly each kind names an opening. Future work first: it is the
# only kind where the author has already described the gap in their own words.
GAP_KINDS: tuple[str, ...] = (
    "future_work",
    "absence",
    "limitation",
    "inefficiency",
    "idealization",
    "breadth",
)

_GAP_MARKERS: dict[str, tuple[str, ...]] = {
    "future_work": (
        "future work", "future research", "future direction", "future study",
        "we leave", "left for future", "remains open", "open problem", "open question",
        "worth exploring", "promising direction", "further investigation",
        "未来工作", "未来研究", "后续工作", "有待进一步", "值得进一步",
    ),
    "absence": (
        "no existing", "no prior", "no work has", "few works", "few studies",
        "little attention", "little work", "not been studied", "not been explored",
        "remains unexplored", "unexplored", "underexplored", "unaddressed",
        "lack of", "lacks a", "has not been", "rarely studied", "no consensus",
        "尚未研究", "研究较少", "缺乏", "鲜有",
    ),
    "limitation": (
        "limitation", "limited to", "only considers", "only consider", "only handles",
        "restricted to", "does not consider", "do not consider", "does not account",
        "ignores", "fails to", "cannot handle", "cannot capture", "beyond the scope",
        "out of scope", "not designed for", "assumes a fixed", "struggles with",
        "局限", "不足之处", "未考虑", "仅考虑", "无法处理", "难以处理",
    ),
    "inefficiency": (
        "computationally expensive", "computationally prohibitive", "too slow",
        "inefficient", "does not scale", "scalability remains", "memory intensive",
        "high computational cost", "quadratic", "expensive to",
        "计算开销", "效率较低", "难以扩展",
    ),
    "idealization": (
        "idealized", "idealised", "ideal assumption", "simplifying assumption",
        "we assume", "assumes that", "under the assumption", "synthetic data",
        "unrealistic", "toy dataset", "controlled setting", "perfect information",
        "理想化", "假设过于", "简化假设",
    ),
    "breadth": (
        "too general", "overly general", "broadly applicable", "not specific",
        "one size fits all", "lacks specificity", "too coarse",
        "过于宽泛", "不够具体",
    ),
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")
_MIN_SENTENCE_CHARS = 40
_MAX_SENTENCE_CHARS = 400
_MIN_TERM_DOCS = 3


def gap_kind(sentence: str) -> str:
    """The kind of shortfall a sentence declares, or ``""`` if it declares none."""
    folded = sentence.casefold()
    for kind in GAP_KINDS:
        for marker in _GAP_MARKERS[kind]:
            if marker in folded:
                return kind
    return ""


def _marker_of(sentence: str) -> str:
    folded = sentence.casefold()
    best = ""
    for kind in GAP_KINDS:
        for marker in _GAP_MARKERS[kind]:
            if marker in folded and len(marker) > len(best):
                best = marker
    return best


def sentences(text: str) -> list[str]:
    """Split prose into candidate sentences, dropping fragments."""
    out: list[str] = []
    for raw in _SENTENCE_SPLIT.split(text or ""):
        sentence = " ".join(raw.split())
        if len(sentence) < _MIN_SENTENCE_CHARS:
            continue
        out.append(sentence[:_MAX_SENTENCE_CHARS])
    return out


def _page_sentences(library: "Library", work: Any) -> list[tuple[int | None, str]]:
    """(page, sentence) pairs for one work, from full text when available."""
    from ..library.passages import split_pages

    fulltext = library.read_fulltext(work)
    if fulltext:
        pairs: list[tuple[int | None, str]] = []
        for page, page_text in split_pages(fulltext):
            for sentence in sentences(page_text):
                pairs.append((page, sentence))
        if pairs:
            return pairs
    abstract = work.abstract()
    if abstract:
        return [(None, sentence) for sentence in sentences(abstract)]
    return []


def _declared_gaps(
    library: "Library",
    works: Iterable[Any],
    *,
    max_per_work: int,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int]]:
    found: list[dict[str, Any]] = []
    coverage = {"with_fulltext": 0, "abstract_only": 0, "no_text": 0}
    for work in works:
        pairs = _page_sentences(library, work)
        if work.has_fulltext() and pairs and pairs[0][0] is not None:
            coverage["with_fulltext"] += 1
        elif pairs:
            coverage["abstract_only"] += 1
        else:
            coverage["no_text"] += 1
        kept = 0
        seen: set[str] = set()
        for page, sentence in pairs:
            kind = gap_kind(sentence)
            if not kind:
                continue
            key = sentence.casefold()
            if key in seen:
                continue
            seen.add(key)
            found.append(
                {
                    "work_id": work.work_id,
                    "title": work.title(),
                    "year": work.year(),
                    "page": page,
                    "kind": kind,
                    "marker": _marker_of(sentence),
                    "sentence": sentence,
                }
            )
            kept += 1
            if kept >= max_per_work:
                break
        if len(found) >= limit:
            break
    found.sort(key=lambda row: (str(row["work_id"]), row["page"] or 0, row["sentence"]))
    found = found[:limit]
    kinds: dict[str, int] = {kind: 0 for kind in GAP_KINDS}
    for row in found:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
    return found, kinds, coverage


def gaps(
    library: "Library",
    survey: dict[str, Any] | str,
    *,
    max_per_work: int = 3,
    limit: int = 60,
    top_pairs: int = 25,
    max_n: int = 2,
) -> dict[str, Any]:
    """Collect the gap evidence for a survey's direction.

    Accepts the survey record or its ``survey_id`` (loaded from the library).
    """
    if isinstance(survey, str):
        loaded = load_json(library, "surveys", survey)
        if loaded is None:
            return {
                "error": "unknown_survey",
                "survey_id": survey,
                "message": (
                    "No stored survey with that id. Run `ccb topics survey \"<direction>\"` "
                    "first; survey ids are not guessable."
                ),
            }
        survey = loaded

    query = str(survey.get("query") or "")
    works: list[Any] = []
    for row in survey.get("works", []):
        wid = str(row.get("work_id") or "")
        if not wid:
            continue
        work = library.load(wid)
        if work is not None:
            works.append(work)

    declared, kinds, coverage = _declared_gaps(
        library, works, max_per_work=max_per_work, limit=limit
    )
    doc_terms = [
        terms_mod.document_terms(w.title() or "", w.abstract() or "", max_n=max_n)
        for w in works
    ]
    ranked = list(survey.get("terms") or []) or terms_mod.term_frequencies(
        doc_terms, top=40, max_n=max_n
    )
    sparse = terms_mod.sparse_pairs(
        doc_terms, ranked, min_docs=_MIN_TERM_DOCS, limit=top_pairs
    )

    evidence_kinds = {k: v for k, v in kinds.items() if v}
    usable = bool(declared) or bool(sparse)
    result: dict[str, Any] = {
        "survey_id": survey.get("survey_id", ""),
        "query": query,
        "coverage": {
            "works": len(works),
            "scanned_with_fulltext": coverage["with_fulltext"],
            "abstract_only": coverage["abstract_only"],
            "no_text": coverage["no_text"],
        },
        "declared_gaps": declared,
        "gap_kinds": evidence_kinds,
        "sparse_pairs": sparse,
        "usable": usable,
    }
    if not usable:
        result["message"] = (
            "No gap evidence found. Either the direction has too few works with stored "
            "full text for anyone to have declared a limitation, or the corpus does not "
            "cover this direction. Add full text (`ccb get <work_id> --with-pdf`) rather "
            "than lowering the bar here."
        )
    elif not declared:
        result["message"] = (
            "No declared gaps were found; only sparse term pairs are available. "
            "Recombination candidates are weaker evidence than an author's own "
            "statement, and should be presented as such."
        )
    return result
