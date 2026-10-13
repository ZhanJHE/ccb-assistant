"""DBLP — the only CS-native bibliography.

DBLP is the best identity spine for computer science: it is curated, venue-aware and
has its own stable record keys. It is also, as of this writing, fronted by an Anubis
anti-bot challenge that answers HTTP 200 with an HTML page. That is handled
explicitly here rather than papered over: the channel reports itself as gated so the
aggregator can degrade to OpenAlex/Crossref/OpenReview and *say so*, instead of
returning an empty result that reads like "nothing exists".
"""

from __future__ import annotations

import re
from typing import Any

from ...core.model import ChannelRecord
from ..net import challenge_reason, is_bot_challenge
from ...core.util import normalize_doi, strip_latex
from .base import (
    CAP_BIBTEX,
    CAP_LOOKUP,
    CAP_SEARCH,
    CAP_VENUE,
    Channel,
    ChannelResult,
    ChannelSpec,
)

API = "https://dblp.org/search/publ/api"
AUTHOR_API = "https://dblp.org/search/author/api"

# DBLP type tokens -> our manifestation vocabulary.
_TYPE_MAP = {
    "conference and workshop papers": "proceedings",
    "journal articles": "journal",
    "informal and other publications": "preprint",
    "books and theses": "repository",
    "editorship": "record",
    "reference works": "record",
    "parts in books or collections": "proceedings",
}


class DblpChannel(Channel):
    # dblp keys and DOIs; it has no arXiv or OpenReview id lookup endpoint.
    supports = ("dblp", "doi", "title")

    spec = ChannelSpec(
        name="dblp",
        kind="http",
        title="dblp computer science bibliography",
        caps=(CAP_SEARCH, CAP_LOOKUP, CAP_VENUE, CAP_BIBTEX),
        auth="none",
        license="CC0 1.0 (dblp data)",
        rate_rps=1.0,
        hosts=("dblp.org",),
        cs_authority=True,
        notes=(
            "Curated CS bibliography; strongest for venue- and author-level "
            "bibliographies and for canonical conference venue names. Carries no "
            "abstracts and no PDFs. Currently reachable only when not gated by its "
            "anti-bot challenge; the channel reports the gate explicitly."
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
        params = {"q": query, "format": "json", "h": max(1, min(limit * 2, 1000))}
        return self._fetch(API, params, limit=limit, year_from=year_from, year_to=year_to)

    def lookup(self, identifier: str, **kw: Any) -> ChannelResult:
        from ...core.ids import parse_identifier

        parsed = parse_identifier(identifier)
        if parsed is None:
            return ChannelResult(self.name, error=f"unrecognized identifier: {identifier!r}")
        # DBLP has no id-lookup endpoint, but its search accepts a DOI or a record
        # key as a term and returns the matching record.
        if parsed.scheme == "dblp":
            term = parsed.value
        elif parsed.scheme == "doi":
            term = parsed.value
        else:
            return ChannelResult(
                self.name,
                error=f"dblp lookup supports dblp keys and DOIs, got {parsed.scheme!r}",
            )
        return self._fetch(API, {"q": term, "format": "json", "h": 10}, limit=5)

    def _fetch(
        self,
        url: str,
        params: dict[str, Any],
        *,
        limit: int,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> ChannelResult:
        data, resp, ev_id = self.request_json(url, params=params, notes="dblp search")
        res = ChannelResult(self.name, ev_id=ev_id, queries=[{"url": url, "params": params}])
        if data is None:
            res.error = resp.error or f"HTTP {resp.status}"
            return res
        if is_bot_challenge(resp.body, resp.content_type):
            res.error = challenge_reason(resp.body, resp.content_type)
            return res
        result = data.get("result") if isinstance(data, dict) else None
        hits = (result or {}).get("hits") if isinstance(result, dict) else None
        if not isinstance(hits, dict):
            res.error = "dblp response has no 'result.hits' object"
            return res
        total = hits.get("@total")
        try:
            res.total_available = int(total) if total is not None else None
        except (TypeError, ValueError):
            res.total_available = None
        raw_hits = hits.get("hit") or []
        if isinstance(raw_hits, dict):
            raw_hits = [raw_hits]
        for h in raw_hits:
            info = (h or {}).get("info") if isinstance(h, dict) else None
            if not isinstance(info, dict):
                continue
            rec = self._parse_info(info, ev_id)
            if rec is None:
                continue
            if year_from and rec.year and rec.year < year_from:
                continue
            if year_to and rec.year and rec.year > year_to:
                continue
            res.records.append(rec)
            if len(res.records) >= limit:
                break
        return res

    def _parse_info(self, info: dict[str, Any], ev_id: str) -> ChannelRecord | None:
        title = strip_latex(str(info.get("title") or "")).strip()
        title = re.sub(r"\s+", " ", title)
        if not title:
            return None
        # DBLP emits a bare object instead of a list when there is exactly one author.
        raw_authors = (info.get("authors") or {}).get("author")
        if raw_authors is None:
            raw_authors = []
        if isinstance(raw_authors, (str, dict)):
            raw_authors = [raw_authors]
        authors: list[str] = []
        for a in raw_authors:
            name = a.get("text") if isinstance(a, dict) else str(a)
            if name:
                authors.append(name.strip())
        year = info.get("year")
        try:
            year = int(year) if year is not None else None
        except (TypeError, ValueError):
            year = None
        venue = str(info.get("venue") or "")
        if isinstance(venue, list):
            venue = venue[0] if venue else ""
        raw_type = str(info.get("type") or "")
        kind = _TYPE_MAP.get(raw_type_casefold(raw_type), "record")
        ee = info.get("ee") or ""
        if isinstance(ee, list):
            ee = ee[0] if ee else ""
        doi = normalize_doi(str(info.get("doi") or ""))
        if not doi and "doi.org/" in str(ee):
            doi = normalize_doi(str(ee))
        return ChannelRecord(
            channel=self.name,
            title=title,
            authors=authors,
            year=year,
            venue=venue,
            venue_type=raw_type,
            doi=doi,
            dblp_key=str(info.get("key") or ""),
            url=str(info.get("url") or ""),
            language="en",
            kind=kind,
            ev=ev_id,
            extras={"dblp_type": raw_type, "ee": ee, "dblp_key": info.get("key")},
        )


def raw_type_casefold(raw_type: str) -> str:
    return (raw_type or "").strip().casefold()
