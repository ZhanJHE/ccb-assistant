"""OpenAlex — the broadest open index, and the best open-access locator.

Two shape quirks the parser must handle:

* the abstract arrives as an ``abstract_inverted_index`` (word -> positions), which
  has to be un-inverted; a naive inversion mis-orders words that appear at multiple
  positions;
* ``meta`` is null on some responses and the count lives under ``meta.count`` when
  present, so a missing total must be reported as unknown rather than as zero.
"""

from __future__ import annotations

import re
from typing import Any

from ...core.model import ChannelRecord
from ...core.util import normalize_doi, strip_latex
from .base import (
    CAP_BIBTEX,
    CAP_CITATIONS,
    CAP_LOOKUP,
    CAP_OA_RESOLVE,
    CAP_SEARCH,
    CAP_VENUE,
    Channel,
    ChannelResult,
    ChannelSpec,
)

API = "https://api.openalex.org/works"
# Validated against the live API rather than guessed: asking OpenAlex for an invalid
# select field makes it answer HTTP 400 *and list the legal ones*. Note that `license`
# is not a top-level select field — it lives inside the location objects, so it is
# read from there.
SELECT = (
    "id,doi,title,display_name,publication_year,publication_date,type,language,"
    "authorships,primary_location,best_oa_location,locations,open_access,"
    "abstract_inverted_index,referenced_works_count,cited_by_count,biblio,"
    "is_retracted,is_paratext"
)


def uninvert(index: dict[str, list[int]] | None, *, max_words: int = 4000) -> str:
    """Rebuild text from an OpenAlex inverted index without mis-ordering words.

    The subtle bug here is that a word occurring at several positions must be placed
    at *all* of them; mapping position -> word and then sorting is the correct
    inversion, whereas iterating the dict and appending produces scrambled text.
    """
    if not index:
        return ""
    positions: dict[int, str] = {}
    for word, idxs in index.items():
        if not isinstance(idxs, list):
            continue
        for i in idxs:
            if isinstance(i, int) and 0 <= i < max_words:
                positions[i] = word
    if not positions:
        return ""
    return " ".join(positions[i] for i in sorted(positions))


class OpenAlexChannel(Channel):
    # Broadest resolver: DOI, PMID, its own id, plus a title search fallback for
    # records it indexes but that cannot be addressed by a stable identifier.
    supports = ("doi", "pmid", "openalex", "title", "arxiv", "openreview",
                "acl", "pmlr")

    spec = ChannelSpec(
        name="openalex",
        kind="http",
        title="OpenAlex (250M+ works, open index)",
        caps=(CAP_SEARCH, CAP_LOOKUP, CAP_OA_RESOLVE, CAP_CITATIONS, CAP_VENUE, CAP_BIBTEX),
        auth="OPENALEX_API_KEY?",
        license="CC0 (data)",
        rate_rps=2.0,
        notes=(
            "Best general-purpose open index and the most reliable open-access "
            "locator. Works keyless; OPENALEX_API_KEY raises the daily budget, "
            "OPENALEX_EMAIL puts us in the polite pool."
        ),
    )

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        year_from: int | None = None,
        year_to: int | None = None,
        **kw: Any,
    ) -> ChannelResult:
        filters = []
        if year_from or year_to:
            lo = year_from or 1000
            hi = year_to or 3000
            filters.append(f"publication_year:{lo}-{hi}")
        params = self.polite_params(
            {
                "search": query,
                "per-page": max(1, min(limit, 200)),
                "select": SELECT,
            }
        )
        if filters:
            params["filter"] = ",".join(filters)
        return self._fetch(params, label="search")

    def lookup(self, identifier: str, **kw: Any) -> ChannelResult:
        """Resolve an identifier precisely, or decline.

        Measured behaviour of this API, which drives the mapping below:

        * ``filter=doi:...`` is exact (count=1 for a known DOI);
        * ``search=<an arXiv id>`` returns ~15,000 loose matches, so treating an
          identifier as free text silently pulls unrelated papers into the library —
          that route is never used for an identifier;
        * ``filter=ids.arxiv:...`` does not exist (HTTP 400).

        So an arXiv id is resolved through its registered DOI (``10.48550/arXiv.<id>``),
        and when nothing can be resolved precisely the channel says so: feeding a wrong
        record into the library is far worse than returning none.
        """
        from ...core.ids import parse_identifier

        parsed = parse_identifier(identifier)
        if parsed is None:
            return ChannelResult(self.name, error=f"unrecognized identifier: {identifier!r}")
        scheme = parsed.scheme
        if scheme == "doi":
            return self._fetch(
                self.polite_params({"filter": f"doi:{parsed.value}", "select": SELECT}),
                label="lookup-doi",
            )
        if scheme == "pmid":
            return self._fetch(
                self.polite_params({"filter": f"pmid:{parsed.value}", "select": SELECT}),
                label="lookup-pmid",
            )
        if scheme == "openalex":
            return self._single(f"{API}/{parsed.value}", label="lookup-id")
        if scheme == "arxiv":
            arxiv_doi = f"10.48550/arxiv.{parsed.value}".casefold()
            res = self._fetch(
                self.polite_params({"filter": f"doi:{arxiv_doi}", "select": SELECT}),
                label="lookup-arxiv-via-doi",
            )
            if not res.records and not res.error:
                res.warnings.append(
                    "OpenAlex has no work registered under the arXiv DOI "
                    f"{arxiv_doi}; the preprint may only exist there as a source record"
                )
            return res
        return ChannelResult(
            self.name,
            error=(
                f"openalex cannot resolve a {scheme!r} identifier precisely; use the "
                "native channel for it rather than a fuzzy search"
            ),
        )

    def lookup_conditional(self, identifier: str) -> ChannelResult:
        """Same four precise routes as `lookup`, as conditional GETs.

        Every lookup URL here is stable (filter by DOI/PMID, or the OpenAlex id itself),
        and OpenAlex answers with ETags — so a re-check of an unchanged work transfers
        no body.
        """
        from ...core.ids import parse_identifier

        parsed = parse_identifier(identifier)
        if parsed is None:
            return self.lookup(identifier)
        if parsed.scheme == "doi":
            return self._fetch(
                self.polite_params({"filter": f"doi:{parsed.value}", "select": SELECT}),
                label="lookup-doi", conditional=True,
            )
        if parsed.scheme == "pmid":
            return self._fetch(
                self.polite_params({"filter": f"pmid:{parsed.value}", "select": SELECT}),
                label="lookup-pmid", conditional=True,
            )
        if parsed.scheme == "openalex":
            return self._single(f"{API}/{parsed.value}", label="lookup-id", conditional=True)
        if parsed.scheme == "arxiv":
            arxiv_doi = f"10.48550/arxiv.{parsed.value}".casefold()
            return self._fetch(
                self.polite_params({"filter": f"doi:{arxiv_doi}", "select": SELECT}),
                label="lookup-arxiv-via-doi", conditional=True,
            )
        return self.lookup(identifier)

    def _single(self, url: str, *, label: str, conditional: bool = False) -> ChannelResult:
        data, resp, ev_id = self.request_json(
            url, params=self.polite_params(), notes=f"openalex {label}",
            conditional=conditional,
        )
        if conditional and resp.status == 304:
            return ChannelResult(self.name, not_modified=True, queries=[{"url": url}])
        res = ChannelResult(self.name, ev_id=ev_id, queries=[{"url": url}])
        if data is None:
            res.error = resp.error or f"HTTP {resp.status}"
            return res
        rec = self._parse_work(data, ev_id)
        if rec is not None:
            res.records.append(rec)
        return res

    def _fetch(self, params: dict[str, Any], *, label: str,
               conditional: bool = False) -> ChannelResult:
        data, resp, ev_id = self.request_json(
            API, params=params, notes=f"openalex {label}", conditional=conditional,
        )
        if conditional and resp.status == 304:
            return ChannelResult(self.name, not_modified=True, queries=[{"url": API}])
        res = ChannelResult(self.name, ev_id=ev_id, queries=[{"url": API, "params": params}])
        if data is None:
            res.error = resp.error or f"HTTP {resp.status}"
            return res
        meta = data.get("meta") if isinstance(data, dict) else None
        if isinstance(meta, dict) and isinstance(meta.get("count"), int):
            res.total_available = meta["count"]
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            res.error = "openalex response has no 'results' list"
            return res
        for w in results:
            rec = self._parse_work(w, ev_id)
            if rec is not None:
                res.records.append(rec)
        return res

    def _parse_work(self, w: dict[str, Any], ev_id: str) -> ChannelRecord | None:
        if not isinstance(w, dict):
            return None
        title = strip_latex(w.get("title") or w.get("display_name") or "").strip()
        title = re.sub(r"\s+", " ", title)
        if not title:
            return None
        doi = normalize_doi(w.get("doi") or "")
        year = w.get("publication_year")
        if not isinstance(year, int):
            year = None
        authors: list[str] = []
        for a in w.get("authorships") or []:
            if not isinstance(a, dict):
                continue
            name = ((a.get("author") or {}).get("display_name") or "").strip()
            if name:
                authors.append(name)
        biblio = w.get("biblio") or {}
        oa = w.get("open_access") or {}
        best = w.get("best_oa_location") or {}
        primary = w.get("primary_location") or {}
        source = (primary.get("source") or {}) if isinstance(primary, dict) else {}
        venue = source.get("display_name") or ""
        pdf_url = (best.get("pdf_url") or "") if isinstance(best, dict) else ""
        if not pdf_url and isinstance(primary, dict):
            pdf_url = primary.get("pdf_url") or ""
        if not pdf_url:
            for loc in w.get("locations") or []:
                if isinstance(loc, dict) and loc.get("pdf_url"):
                    pdf_url = loc["pdf_url"]
                    break
        landing = (best.get("landing_page_url") if isinstance(best, dict) else "") or (
            primary.get("landing_page_url") if isinstance(primary, dict) else ""
        )
        # OpenAlex types are lowercase nouns; map to our manifestation vocabulary.
        wtype = (w.get("type") or "").casefold()
        kind = {
            "article": "journal",
            "preprint": "preprint",
            "proceedings-article": "proceedings",
            "book-chapter": "proceedings",
            "posted-content": "preprint",
            "dissertation": "repository",
            "report": "repository",
        }.get(wtype, "record")
        oa_status = (oa.get("oa_status") or "") if isinstance(oa, dict) else ""
        lic = (best.get("license") or "") if isinstance(best, dict) else ""
        return ChannelRecord(
            channel=self.name,
            title=title,
            authors=authors,
            year=year,
            venue=venue,
            venue_type=wtype,
            abstract=strip_latex(uninvert(w.get("abstract_inverted_index"))).strip(),
            doi=doi,
            url=landing or (f"https://doi.org/{doi}" if doi else w.get("id", "")),
            pdf_url=pdf_url,
            oa_status=oa_status,
            license=lic,
            language=(w.get("language") or "") or "",
            volume=str(biblio.get("volume") or ""),
            issue=str(biblio.get("issue") or ""),
            pages=(
                f"{biblio.get('first_page')}-{biblio.get('last_page')}"
                if biblio.get("first_page") and biblio.get("last_page")
                else str(biblio.get("first_page") or "")
            ),
            kind=kind,
            openalex_id=(w.get("id") or "").rsplit("/", 1)[-1],
            ev=ev_id,
            extras={
                "openalex_id": (w.get("id") or "").rsplit("/", 1)[-1],
                "cited_by_count": w.get("cited_by_count"),
                "referenced_works_count": w.get("referenced_works_count"),
                "publication_date": w.get("publication_date"),
                "is_oa": bool(oa.get("is_oa")) if isinstance(oa, dict) else False,
            },
        )
