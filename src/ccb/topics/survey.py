"""Domain survey: what the corpus actually holds for a direction.

Before a topic can be mined, two questions have to be answered honestly: *which*
papers does the library hold for this direction, and is that enough to mine at all?
A survey answers both, and it answers them with counts and lists rather than with a
summary, so every later claim can be traced back to a specific work.

When the direction is too thin to mine, the survey tops it up from the channels —
reusing the search module rather than a second, divergent acquisition path — and
reports exactly what it added. Under ``--offline`` it does not try, and says the
corpus was left as it is; "could not look" and "nothing there" stay distinguishable,
as everywhere else in this tool.

The survey record is a pure function of (query, window, corpus contents), so the same
inputs produce the same ``survey_id`` and the same numbers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

from ..core.util import normalize_text, short_hash
from . import terms as terms_mod
from .ccf import CcfCatalog, default_catalog

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..library.store import Library
    from ..search.acquire import Resolver

DEFAULT_MIN_WORKS = 20
DEFAULT_MIN_FULLTEXT = 5
DEFAULT_LIMIT = 200


def _work_terms(work: Any, *, max_n: int) -> set[str]:
    return terms_mod.document_terms(work.title() or "", work.abstract() or "", max_n=max_n)


def _collect_works(
    library: "Library",
    query: str,
    *,
    limit: int,
    year_from: int | None,
    year_to: int | None,
) -> tuple[list[Any], str]:
    """The works matching ``query``, plus how they were found.

    The full-text index is the first choice, but it is an AND-ish match: a query like
    "graph neural networks for molecules" can miss papers that any single term would
    find. When the index comes back thin the survey falls back to a keyword scan over
    title and abstract, so a survey is never quietly starved by query syntax.
    """
    if not query.strip():
        works = [
            w
            for w in library.iter_works()
            if (year_from is None or (w.year() or 0) >= year_from)
            and (year_to is None or (w.year() or 0) <= year_to)
        ]
        works.sort(key=lambda w: (-(w.year() or 0), w.work_id))
        return works[:limit], "whole-library scan"

    hits = library.search(query, limit=limit, year_from=year_from, year_to=year_to)
    works: list[Any] = []
    seen: set[str] = set()
    for hit in hits:
        wid = hit.get("work_id", "")
        if wid and wid not in seen:
            seen.add(wid)
            loaded = library.load(wid)
            if loaded is not None:
                works.append(loaded)

    if len(works) >= min(limit, 5):
        return works, "full-text index"

    keywords = [
        token
        for token in normalize_text(query).split()
        if len(token) > 2 and token not in terms_mod.STOPWORDS
    ]
    if not keywords:
        return works, "full-text index"

    for work in library.iter_works():
        if work.work_id in seen:
            continue
        if year_from is not None and (work.year() or 0) < year_from:
            continue
        if year_to is not None and (work.year() or 0) > year_to:
            continue
        haystack = normalize_text(f"{work.title()} {work.abstract()}")
        if any(keyword in haystack for keyword in keywords):
            seen.add(work.work_id)
            works.append(work)
        if len(works) >= limit:
            break
    return works, "full-text index, widened by keyword scan"


def _venue_rows(works: Iterable[Any], catalog: CcfCatalog) -> tuple[list[dict[str, Any]], dict[str, int]]:
    grouped: dict[str, dict[str, Any]] = {}
    ccf_counts = {"A": 0, "B": 0, "C": 0, "unmatched": 0}
    for work in works:
        venue = (work.venue() or "").strip()
        key = normalize_text(venue) or "(none)"
        row = grouped.setdefault(
            key, {"venue": venue or "(none)", "works": 0, "ccf": "", "matched_as": ""}
        )
        row["works"] += 1
        match = catalog.match(venue) if venue else None
        if match is not None:
            row["ccf"] = match.rank
            row["matched_as"] = match.abbr
            ccf_counts[match.rank] = ccf_counts.get(match.rank, 0) + 1
        else:
            ccf_counts["unmatched"] += 1
    rows = sorted(grouped.values(), key=lambda r: (-r["works"], r["venue"]))
    return rows, ccf_counts


def _year_rows(works: Iterable[Any]) -> dict[str, int]:
    years: dict[str, int] = {}
    for work in works:
        year = work.year()
        key = str(year) if year else "(unknown)"
        years[key] = years.get(key, 0) + 1
    return dict(sorted(years.items()))


def _top_authors(works: Iterable[Any], *, limit: int = 15) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for work in works:
        seen: set[str] = set()
        for author in work.authors():
            key = author.strip()
            if not key or key.casefold() in seen:
                continue
            seen.add(key.casefold())
            counts[key] = counts.get(key, 0) + 1
    ranked = [{"author": name, "works": n} for name, n in counts.items()]
    ranked.sort(key=lambda r: (-r["works"], r["author"]))
    return ranked[:limit]


def _work_rows(works: Iterable[Any], catalog: CcfCatalog) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for work in works:
        venue = work.venue() or ""
        match = catalog.match(venue) if venue else None
        rows.append(
            {
                "work_id": work.work_id,
                "title": work.title(),
                "year": work.year(),
                "venue": venue,
                "ccf": match.rank if match else "",
                "has_pdf": work.has_pdf(),
                "has_fulltext": work.has_fulltext(),
                "has_abstract": bool(work.abstract()),
            }
        )
    return rows


def _expand(
    library: "Library",
    resolver: "Resolver",
    query: str,
    *,
    year_from: int | None,
    year_to: int | None,
    want_works: int,
    want_fulltext: int,
    max_fetch: int,
) -> dict[str, Any]:
    """Top the direction up from the channels, then index what arrived."""
    report: dict[str, Any] = {"attempted": True, "added": 0, "indexed": 0, "errors": {}}
    try:
        found = resolver.find(
            query,
            limit=max(want_works, DEFAULT_MIN_WORKS),
            year_from=year_from,
            year_to=year_to,
            ingest=True,
        )
    except Exception as exc:  # a channel failure must not fail the survey
        report["errors"]["find"] = f"{type(exc).__name__}: {exc}"
        return report
    report["added"] = found.ingested
    report["channels_queried"] = found.channels_queried
    report["errors"].update(found.errors)
    if found.warnings:
        report["warnings"] = found.warnings

    # Fetch text only for the works that could supply it, and stop as soon as the
    # direction has enough full text to mine.
    fetched = 0
    # Counted once, not inside the loop: the previous version re-walked every work file
    # on every iteration (O(n^2) on a corpus of any size).
    with_text = sum(1 for w in library.iter_works() if w.has_fulltext())
    for work in library.iter_works():
        if fetched >= max_fetch or with_text >= want_fulltext:
            break
        if not work.has_pdf() and not work.best_pdf():
            continue
        had_text = work.has_fulltext()
        try:
            # `extract=True` is the point of this loop. Without it, a work whose PDF is
            # already stored but was never read — the common case after a batch download
            # or a migration — passed the guard and then did nothing, so `--min-fulltext`
            # could never be satisfied by the top-up it names.
            result = resolver.get(work.work_id, with_pdf=True, extract=True)
        except Exception as exc:
            report["errors"][work.work_id] = f"{type(exc).__name__}: {exc}"
            continue
        report["errors"].update(result.errors)
        # Re-read: `work` was loaded before the call and `get` attaches the text to its
        # own instance, so the stale object answers for the state that no longer holds.
        after = library.load(result.work_id or work.work_id, use_cache=False)
        if after is not None and after.has_fulltext() and not had_text:
            report["indexed"] += 1
            with_text += 1
        fetched += 1
    return report


def survey(
    library: "Library",
    query: str,
    *,
    resolver: "Resolver | None" = None,
    offline: bool = False,
    min_works: int = DEFAULT_MIN_WORKS,
    min_fulltext: int = DEFAULT_MIN_FULLTEXT,
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int = DEFAULT_LIMIT,
    top_terms: int = 40,
    max_n: int = 2,
    catalog: CcfCatalog | None = None,
) -> dict[str, Any]:
    """Map the corpus for ``query``, topping it up from channels when it is thin."""
    library.ensure()
    catalog = catalog or default_catalog()
    notes: list[str] = []

    works, found_via = _collect_works(
        library, query, limit=limit, year_from=year_from, year_to=year_to
    )
    with_fulltext = [w for w in works if w.has_fulltext()]
    insufficient = len(works) < min_works or len(with_fulltext) < min_fulltext

    expansion: dict[str, Any] | None = None
    if insufficient:
        if offline:
            notes.append(
                f"Offline: the corpus was left as it is ({len(works)} works, "
                f"{len(with_fulltext)} with full text) and was not topped up from "
                f"channels."
            )
        elif resolver is None:
            notes.append(
                "No channel access was available, so the corpus was not topped up. "
                f"Run `ccb find \"{query}\"` and `ccb get <work_id> --with-pdf` to add "
                f"works, or call this again with a resolver."
            )
        else:
            expansion = _expand(
                library,
                resolver,
                query,
                year_from=year_from,
                year_to=year_to,
                want_works=min_works,
                want_fulltext=min_fulltext,
                max_fetch=max(min_fulltext, 5),
            )
            works, found_via = _collect_works(
                library, query, limit=limit, year_from=year_from, year_to=year_to
            )
            with_fulltext = [w for w in works if w.has_fulltext()]
            insufficient = len(works) < min_works or len(with_fulltext) < min_fulltext

    doc_terms = [_work_terms(w, max_n=max_n) for w in works]
    ranked_terms = terms_mod.term_frequencies(doc_terms, top=top_terms, max_n=max_n)
    latin_docs = sum(1 for t in doc_terms if t)
    if works and latin_docs < max(2, len(works) // 4):
        notes.append(
            "Few works carry Latin-script title or abstract text, so the term layer is "
            "thin and gap mining will have little to work with."
        )

    venues, ccf_counts = _venue_rows(works, catalog)
    survey_id = short_hash(
        "survey",
        normalize_text(query),
        ",".join(sorted(w.work_id for w in works)),
        str(year_from or ""),
        str(year_to or ""),
    )

    result: dict[str, Any] = {
        "survey_id": survey_id,
        "query": query,
        "found_via": found_via,
        "window": {"year_from": year_from, "year_to": year_to},
        "corpus": {
            "works": len(works),
            "with_pdf": sum(1 for w in works if w.has_pdf()),
            "with_fulltext": len(with_fulltext),
            "with_abstract": sum(1 for w in works if w.abstract()),
        },
        "thresholds": {"min_works": min_works, "min_fulltext": min_fulltext},
        "sufficient": not insufficient,
        "years": _year_rows(works),
        "venues": venues,
        "ccf": ccf_counts,
        "top_authors": _top_authors(works),
        "terms": ranked_terms,
        "works": _work_rows(works, catalog),
    }
    if expansion is not None:
        result["expansion"] = expansion
    if insufficient:
        result["message"] = (
            f"Not enough evidence to mine: {len(works)} work(s) and {len(with_fulltext)} "
            f"with full text, against thresholds of {min_works} and {min_fulltext}. "
            f"Gap mining over this corpus would produce claims that cannot be checked."
        )
    if notes:
        result["notes"] = notes
    result["catalog"] = {"source": catalog.source, "venues": len(catalog.venues)}
    return result


def save_survey(library: "Library", record: dict[str, Any]) -> str:
    """Persist a survey so `gaps <survey_id>` can find it again."""
    from .store import save_json

    survey_id = str(record.get("survey_id") or "")
    if not survey_id:
        raise ValueError("survey record has no survey_id")
    save_json(library, "surveys", survey_id, record)
    return survey_id


def load_survey(library: "Library", survey_id: str) -> dict[str, Any] | None:
    from .store import load_json

    return load_json(library, "surveys", survey_id)
