"""Crossref — publisher-of-record DOI metadata.

Crossref is the authority for "what was actually published", so its claims
generally outrank aggregator records in the trust order. Two shape notes:

* abstracts, when present, are JATS XML fragments inside a JSON string and must be
  stripped of tags;
* ``link`` entries advertise text-and-data-mining PDFs, but many are gated behind a
  publisher login despite being listed, so a listed link is a *candidate*, not a
  guarantee — the download layer verifies the bytes are really a PDF.
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
    CAP_SEARCH,
    CAP_VENUE,
    Channel,
    ChannelResult,
    ChannelSpec,
)

API = "https://api.crossref.org/works"
_TAG = re.compile(r"<[^>]+>")
_JATS_TITLE = re.compile(r"<jats:title[^>]*>(.*?)</jats:title>", re.IGNORECASE | re.DOTALL)


def clean_jats(raw: str) -> str:
    """Strip JATS/XML tags and unwrap titles from a Crossref abstract field."""
    if not raw:
        return ""
    text = _JATS_TITLE.sub(r"\1. ", raw)
    text = _TAG.sub(" ", text)
    text = (
        text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#x2010;", "-")
    )
    return re.sub(r"\s+", " ", text).strip()


class CrossrefChannel(Channel):
    # Crossref is a DOI registration agency: a DOI is the only thing it resolves.
    supports = ("doi",)

    spec = ChannelSpec(
        name="crossref",
        kind="http",
        title="Crossref (DOI registration agency metadata)",
        caps=(CAP_SEARCH, CAP_LOOKUP, CAP_CITATIONS, CAP_VENUE, CAP_BIBTEX),
        auth="none",
        license="Crossref metadata is openly available (CC0 for the metadata itself)",
        rate_rps=2.0,
        notes=(
            "Authoritative for published DOI metadata: container title, volume, "
            "issue, pages, publisher. Abstracts are present only when the publisher "
            "deposited them. Set CCB_MAILTO to join the polite pool."
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
        params: dict[str, Any] = {
            "query.bibliographic": query,
            "rows": max(1, min(limit, 100)),
            "select": (
                "DOI,title,author,issued,container-title,type,page,volume,issue,"
                "publisher,abstract,URL,link,license,short-container-title,"
                "published,published-print,published-online,is-referenced-by-count"
            ),
        }
        if year_from or year_to:
            lo = year_from or 1000
            hi = year_to or 3000
            params["filter"] = f"from-pub-date:{lo}-01-01,until-pub-date:{hi}-12-31"
        params = self.polite_params(params)
        return self._fetch(API, params, label="search")

    def lookup(self, identifier: str, **kw: Any) -> ChannelResult:
        from ...core.ids import parse_identifier

        parsed = parse_identifier(identifier)
        if parsed is None:
            return ChannelResult(self.name, error=f"unrecognized identifier: {identifier!r}")
        if parsed.scheme != "doi":
            # Only DOIs are addressable here; say so instead of guessing.
            return ChannelResult(
                self.name,
                error=f"crossref resolves DOIs only, got scheme {parsed.scheme!r}",
            )
        return self._single(f"{API}/{parsed.value}")

    def _single(self, url: str) -> ChannelResult:
        data, resp, ev_id = self.request_json(
            url, params=self.polite_params(), notes="crossref lookup-doi"
        )
        res = ChannelResult(self.name, ev_id=ev_id, queries=[{"url": url}])
        if data is None:
            res.error = resp.error or f"HTTP {resp.status}"
            return res
        msg = data.get("message") if isinstance(data, dict) else None
        if not isinstance(msg, dict):
            res.error = "crossref response has no 'message' object"
            return res
        rec = self._parse_item(msg, ev_id)
        if rec is not None:
            res.records.append(rec)
        return res

    def _fetch(self, url: str, params: dict[str, Any], *, label: str) -> ChannelResult:
        data, resp, ev_id = self.request_json(url, params=params, notes=f"crossref {label}")
        res = ChannelResult(self.name, ev_id=ev_id, queries=[{"url": url, "params": params}])
        if data is None:
            res.error = resp.error or f"HTTP {resp.status}"
            return res
        msg = data.get("message") if isinstance(data, dict) else None
        if not isinstance(msg, dict):
            res.error = "crossref response has no 'message' object"
            return res
        total = msg.get("total-results")
        if isinstance(total, int):
            res.total_available = total
        items = msg.get("items")
        if not isinstance(items, list):
            res.error = "crossref response has no 'items' list"
            return res
        for it in items:
            rec = self._parse_item(it, ev_id)
            if rec is not None:
                res.records.append(rec)
        return res

    def _parse_item(self, it: dict[str, Any], ev_id: str) -> ChannelRecord | None:
        if not isinstance(it, dict):
            return None
        titles = it.get("title") or []
        title = strip_latex(titles[0] if titles else "").strip()
        title = re.sub(r"\s+", " ", title)
        if not title:
            return None
        doi = normalize_doi(it.get("DOI") or "")
        year = None
        for key in ("issued", "published", "published-print", "published-online"):
            parts = ((it.get(key) or {}).get("date-parts") or [[]])[0]
            if parts and isinstance(parts[0], int):
                year = parts[0]
                break
        authors: list[str] = []
        for a in it.get("author") or []:
            if not isinstance(a, dict):
                continue
            given = (a.get("given") or "").strip()
            family = (a.get("family") or "").strip()
            name = (f"{given} {family}".strip() or a.get("name") or "").strip()
            if name:
                authors.append(name)
        containers = it.get("container-title") or it.get("short-container-title") or []
        venue = containers[0] if containers else ""
        ctype = (it.get("type") or "").casefold()
        kind = {
            "journal-article": "journal",
            "proceedings-article": "proceedings",
            "book-chapter": "proceedings",
            "posted-content": "preprint",
            "report": "repository",
            "dissertation": "repository",
        }.get(ctype, "record")
        pdf_url = ""
        for link in it.get("link") or []:
            if not isinstance(link, dict):
                continue
            url = link.get("URL") or ""
            ct = (link.get("content-type") or "").casefold()
            if url and ("pdf" in ct or url.casefold().endswith(".pdf")):
                pdf_url = url
                break
        licenses = it.get("license") or []
        lic = ""
        if licenses and isinstance(licenses[0], dict):
            lic = licenses[0].get("URL") or ""
        return ChannelRecord(
            channel=self.name,
            title=title,
            authors=authors,
            year=year,
            venue=venue,
            venue_type=ctype,
            abstract=clean_jats(it.get("abstract") or ""),
            doi=doi,
            url=it.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
            pdf_url=pdf_url,
            license=lic,
            language=(it.get("language") or "") or "",
            volume=str(it.get("volume") or ""),
            issue=str(it.get("issue") or ""),
            pages=str(it.get("page") or ""),
            publisher=(it.get("publisher") or "") or "",
            kind=kind,
            ev=ev_id,
            extras={
                "crossref_type": ctype,
                "is_referenced_by_count": it.get("is-referenced-by-count"),
            },
        )
