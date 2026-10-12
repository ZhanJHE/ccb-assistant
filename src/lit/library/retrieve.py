"""Grounded retrieval and full-text extraction over the local corpus.

Both operations here are entirely offline. They read work records and write the
derived artefacts that live beside them (extracted text, the passage index), and
neither one ever reaches for a channel. That is why they belong to the library
module: `search` is allowed to depend on this package, not the other way round.

`ask` returns evidence, not prose — ranked passages anchored to ``work_id`` and page
number — so any claim built on them can be checked. Ranking is deterministic, so the
same question yields the same citations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

from ..core.extract import extract_text
from ..core.model import WorkRecord
from ..core.util import sha256_text
from .passages import PassageIndex, chunk_text

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from .store import Library


def ask(
    library: "Library",
    query: str,
    *,
    limit: int = 5,
    work_ids: Iterable[str] | None = None,
    max_per_work: int = 2,
    passages_around: int = 0,
) -> dict[str, Any]:
    """Retrieve the passages that answer a query, with checkable citations."""
    works: list[WorkRecord] = []
    if work_ids:
        for wid in work_ids:
            w = library.resolve(wid)
            if w is not None:
                works.append(w)
    else:
        # Deliberately the *whole* corpus, not just the indexed part. Filtering to
        # works that already have text would make "this paper has no stored full
        # text" indistinguishable from "nothing matched", and an agent cannot act on
        # an ambiguity like that. Works lacking text are reported under `skipped`.
        works = list(library.iter_works())

    all_passages: list[Any] = []
    skipped: list[dict[str, str]] = []
    for w in works:
        ps = library.read_passages(w)
        if not ps:
            skipped.append(
                {"work_id": w.work_id, "reason": "no stored full text to search"}
            )
            continue
        all_passages.extend(ps)

    index = PassageIndex(all_passages)
    for w in works:
        index.set_metadata(w.work_id, title=w.title(), year=w.year())

    hits = index.search(
        query,
        limit=limit,
        work_ids=[w.work_id for w in works] if work_ids else None,
        max_per_work=max_per_work,
    )
    result: dict[str, Any] = {
        "query": query,
        "grounded": bool(hits),
        # Explicit and branchable: "the corpus does not cover this" is an outcome, not
        # an error. Callers that only read exit codes cannot otherwise tell a gap in
        # coverage from a failure to look.
        "outcome": "answered" if hits else "not-covered",
        "corpus": index.stats(),
        "hits": [h.as_dict() for h in hits],
        "note": (
            "These are retrieved passages with page anchors, not generated prose. "
            "Compose the answer from them and cite the cited work_id + page. If "
            "grounded is false, say the corpus does not cover the question rather "
            "than answering from memory."
        ),
    }
    if skipped:
        result["skipped"] = skipped
    if not hits:
        result["message"] = (
            "No stored passage matches this query. Either add papers to the corpus "
            "(`lit find` then `lit get --with-pdf`) or rephrase using terms that "
            "appear in the source text."
        )
    return result


def extract_into(library: "Library", work: WorkRecord) -> dict[str, Any]:
    """Extract and store full text for a work that already has a local PDF."""
    best = work.best_pdf()
    if best is None or not best.pdf_path:
        return {"error": "no local PDF to extract"}
    result = extract_text(library.file_abs(best.pdf_path))
    out = result.as_dict()
    if result.text:
        rel, chars = library.store_fulltext(work.work_id, result.text)
        library.attach_fulltext(work.work_id, rel_path=rel, chars=chars, mid=best.mid)
        out["stored_path"] = rel
        out["chars"] = chars
        # Build the passage index now, while the text is already in memory, and bind
        # it to this text's digest so a later re-extraction invalidates it instead of
        # leaving searches pointed at text that is no longer on disk.
        passages = chunk_text(result.text, work_id=work.work_id)
        if passages:
            _, n = library.store_passages(
                work.work_id, passages, source_sha256=sha256_text(result.text)
            )
            out["passages"] = n
            out["pages_indexed"] = max((p.page for p in passages), default=0)
    return out
