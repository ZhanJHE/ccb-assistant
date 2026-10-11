"""arXiv — preprints, and the authoritative source for LaTeX originals.

Parsed from the Atom feed rather than JSON because that is what arXiv serves. Two
traps the parser must handle (both observed in practice):

* a malformed query yields HTTP 200 with a feed containing a single entry titled
  ``Error`` — parsed naively this becomes a paper called "Error";
* throttling returns plain text ``Rate exceeded.`` rather than XML, so an XML parse
  error must not be reported as "no results".
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from ..model import ChannelRecord
from ..util import normalize_arxiv_id, normalize_doi, strip_latex
from .base import (
    CAP_FULLTEXT,
    CAP_LOOKUP,
    CAP_PDF,
    CAP_SEARCH,
    CAP_VENUE,
    Channel,
    ChannelResult,
    ChannelSpec,
)

API = "http://export.arxiv.org/api/query"
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# ai, cl, cv, lg, ne, stat are the CS-relevant categories; a bare topic query is
# matched across all fields and then noted with its primary category so callers can
# decide relevance themselves.
_DEFAULT_MAX = 30


class ArxivChannel(Channel):
    # arXiv ids, plus titles when that is all the caller has (the search API's
    # relevance ranking is loose, so a title lookup is a fallback, not precision).
    supports = ("arxiv", "title")

    # arXiv's export API intermittently answers 404 under load (observed on repeated
    # identical requests); a retry is cheaper than reporting the source unavailable.
    extra_retry_codes = (404,)

    spec = ChannelSpec(
        name="arxiv",
        kind="http",
        title="arXiv preprint server",
        caps=(CAP_SEARCH, CAP_LOOKUP, CAP_PDF, CAP_FULLTEXT, CAP_VENUE),
        auth="none",
        license="arXiv non-exclusive licence (per-paper terms vary; many are CC-BY)",
        rate_rps=0.34,  # arXiv asks for >= 3 seconds between requests
        cs_authority=True,
        notes=(
            "Authoritative for CS/ML preprints and the LaTeX source. Relevance "
            "ranking of the search API is weak: it matches loosely, so treat arXiv "
            "as an identifier and full-text source, and rank with OpenAlex/DBLP."
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
        q = query
        if year_from or year_to:
            lo = f"{year_from}01010000" if year_from else "000001010000"
            hi = f"{year_to}12312359" if year_to else "999912312359"
            q = f"({q}) AND submittedDate:[{lo} TO {hi}]"
        return self._query(q, limit=limit, label="search")

    def lookup(self, identifier: str, **kw: Any) -> ChannelResult:
        aid = normalize_arxiv_id(identifier)
        if not aid:
            return ChannelResult(self.name, error=f"not an arXiv id: {identifier!r}")
        return self._query("", limit=1, id_list=aid, label="lookup")

    def _query(
        self,
        query: str,
        *,
        limit: int,
        id_list: str = "",
        label: str = "",
    ) -> ChannelResult:
        params: dict[str, Any] = {
            "max_results": max(1, min(limit, _DEFAULT_MAX)),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        if id_list:
            params["id_list"] = id_list
        else:
            params["search_query"] = query
        body, resp, ev_id = self.request_text(
            API, params=params, accept="application/atom+xml", notes=f"arxiv {label}"
        )
        res = ChannelResult(self.name, ev_id=ev_id, queries=[{"url": API, "params": params}])
        if not resp.ok:
            res.error = resp.error or f"HTTP {resp.status}"
            return res
        head = (body or "").lstrip()
        if not head.startswith("<"):
            # arXiv returns "Rate exceeded." as plain text with a 200.
            res.error = f"arXiv did not return a feed: {head[:200]!r}"
            return res
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            res.error = f"arXiv feed is not well-formed XML: {exc}"
            return res
        total = root.findtext("opensearch:totalResults", default="", namespaces={
            "opensearch": "http://a9.com/-/spec/opensearch/1.1/"
        })
        if total.isdigit():
            res.total_available = int(total)
        for entry in root.findall("atom:entry", NS):
            rec = self._parse_entry(entry, ev_id)
            if rec is None:
                continue
            res.records.append(rec)
        if not res.records:
            res.warnings.append("arXiv returned no entries for this query")
        return res

    def _parse_entry(self, entry: ET.Element, ev_id: str) -> ChannelRecord | None:
        title = strip_latex(_text(entry, "atom:title")).strip()
        title = re.sub(r"\s+", " ", title)
        raw_id = _text(entry, "atom:id").strip()
        aid = normalize_arxiv_id(raw_id)
        # The documented failure mode: a bad parameter yields one entry named "Error".
        if title.casefold() == "error" or not aid:
            return None
        authors: list[str] = []
        for a in entry.findall("atom:author", NS):
            name = _text(a, "atom:name").strip()
            if name:
                authors.append(name)
        published = _text(entry, "atom:published") or _text(entry, "atom:updated")
        year = None
        m = re.match(r"(\d{4})", published or "")
        if m:
            year = int(m.group(1))
        doi = normalize_doi(_text(entry, "arxiv:doi"))
        journal_ref = _text(entry, "arxiv:journal_ref").strip()
        comment = _text(entry, "arxiv:comment").strip()
        primary = entry.find("arxiv:primary_category", NS)
        categories = [c.get("term", "") for c in entry.findall("atom:category", NS)]
        pdf_url = ""
        abs_url = ""
        for link in entry.findall("atom:link", NS):
            rel = link.get("rel", "")
            typ = link.get("type", "")
            href = link.get("href", "")
            if rel == "related" and typ == "application/pdf":
                pdf_url = href
            elif rel == "alternate":
                abs_url = href
        if not pdf_url and aid:
            pdf_url = f"https://arxiv.org/pdf/{aid}"
        elif pdf_url:
            # arXiv advertises a *versioned* PDF URL (/pdf/1706.03762v7). Identity and
            # storage here are per-manifestation rather than per-version, so the URL is
            # normalized to the versionless form; otherwise the same paper appears to
            # have changed every time a new arXiv version is posted.
            pdf_url = re.sub(r"(arxiv\.org/pdf/[^/?#]+?)v\d+", r"\1", pdf_url)
        abstract = re.sub(r"\s+", " ", strip_latex(_text(entry, "atom:summary"))).strip()
        venue = journal_ref or (f"arXiv {primary.get('term')}" if primary is not None else "arXiv")
        return ChannelRecord(
            channel=self.name,
            title=title,
            authors=authors,
            year=year,
            venue=venue,
            venue_type="preprint",
            abstract=abstract,
            doi=doi,
            arxiv_id=aid,
            url=abs_url or f"https://arxiv.org/abs/{aid}",
            pdf_url=pdf_url,
            oa_status="green" if pdf_url else "",
            license="arXiv (per-paper)",
            language="en",
            kind="preprint",
            ev=ev_id,
            extras={
                "categories": [c for c in categories if c],
                "primary_category": primary.get("term", "") if primary is not None else "",
                "comment": comment,
                "journal_ref": journal_ref,
                "updated": _text(entry, "atom:updated"),
            },
        )


def _text(node: ET.Element, path: str) -> str:
    found = node.find(path, NS)
    return (found.text or "") if found is not None and found.text else ""
