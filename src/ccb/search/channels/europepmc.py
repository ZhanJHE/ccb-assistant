"""Europe PMC — life-sciences and biomedical literature, with real full text.

Included in a CS-oriented tool on purpose: computer-science work in bioinformatics,
medical imaging and clinical ML is routinely indexed here and nowhere else, and it is
the one channel that returns genuinely searchable full text rather than just an
abstract. It needs no key and no email, which also makes it a useful always-available
fallback when keyed channels degrade.
"""

from __future__ import annotations

import re
from typing import Any

from ...core.model import ChannelRecord
from ...core.util import normalize_doi, strip_latex
from .base import (
    CAP_BIBTEX,
    CAP_FULLTEXT,
    CAP_LOOKUP,
    CAP_SEARCH,
    CAP_VENUE,
    Channel,
    ChannelResult,
    ChannelSpec,
)

API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


class EuropePmcChannel(Channel):
    supports = ("doi", "pmid", "title")

    spec = ChannelSpec(
        name="europepmc",
        kind="http",
        title="Europe PMC (biomedical and life-sciences literature)",
        caps=(CAP_SEARCH, CAP_LOOKUP, CAP_FULLTEXT, CAP_VENUE, CAP_BIBTEX),
        auth="none",
        license="Metadata is open; full text availability is per-article (OA subset)",
        rate_rps=1.0,
        hosts=("www.ebi.ac.uk", "europepmc.org"),
        notes=(
            "No key and no email required, so it is a dependable fallback. Use it for "
            "biomedical/clinical work; it also indexes preprints via SRC:\"PPR\". The API "
            "host (www.ebi.ac.uk) is open; the europepmc.org full-text pages are behind a "
            "browser gate that answers 403 to this client even with a browser User-Agent, "
            "so no fetchable pdf_url is claimed — the links the API declares are carried in "
            "each record's extras.fulltext_urls instead."
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
            q = f"({q}) AND (FIRST_PDATE:[{year_from or 1800}-01-01 TO {year_to or 3000}-12-31])"
        params = {
            "query": q,
            "format": "json",
            "pageSize": max(1, min(limit, 100)),
            "resultType": "core",
        }
        return self._fetch(params, label="search")

    def lookup(self, identifier: str, **kw: Any) -> ChannelResult:
        from ...core.ids import parse_identifier

        parsed = parse_identifier(identifier)
        if parsed is None:
            return ChannelResult(self.name, error=f"unrecognized identifier: {identifier!r}")
        if parsed.scheme == "doi":
            return self._fetch(
                {"query": f'DOI:"{parsed.value}"', "format": "json", "pageSize": 3,
                 "resultType": "core"},
                label="lookup-doi",
            )
        if parsed.scheme == "pmid":
            return self._fetch(
                {"query": f"EXT_ID:{parsed.value}", "format": "json", "pageSize": 3,
                 "resultType": "core"},
                label="lookup-pmid",
            )
        return ChannelResult(
            self.name, error=f"europepmc resolves DOI and PMID, got {parsed.scheme!r}"
        )

    def _fetch(self, params: dict[str, Any], *, label: str) -> ChannelResult:
        data, resp, ev_id = self.request_json(API, params=params, notes=f"europepmc {label}")
        res = ChannelResult(self.name, ev_id=ev_id, queries=[{"url": API, "params": params}])
        if data is None:
            res.error = resp.error or f"HTTP {resp.status}"
            return res
        # Europe PMC reports failures as errCode inside a 200 body.
        if isinstance(data, dict) and data.get("errCode"):
            res.error = f"europepmc errCode={data.get('errCode')}: {data.get('errMsg', '')}"[:300]
            return res
        body = data.get("resultList") if isinstance(data, dict) else None
        items = (body or {}).get("result") if isinstance(body, dict) else None
        if not isinstance(items, list):
            res.error = "europepmc response has no resultList.result list"
            return res
        total = data.get("hitCount") if isinstance(data, dict) else None
        if isinstance(total, int):
            res.total_available = total
        for item in items:
            rec = self._parse(item, ev_id)
            if rec is not None:
                res.records.append(rec)
        return res

    def _parse(self, item: dict[str, Any], ev_id: str) -> ChannelRecord | None:
        if not isinstance(item, dict):
            return None
        title = strip_latex(str(item.get("title") or "")).strip()
        title = re.sub(r"\s+", " ", title).rstrip(".")
        if not title:
            return None
        authors = str(item.get("authorString") or "").strip().rstrip(".")
        author_list = [a.strip() for a in authors.split(",") if a.strip()] if authors else []
        year = item.get("pubYear")
        try:
            year = int(year) if year is not None else None
        except (TypeError, ValueError):
            year = None
        journal = ((item.get("journalInfo") or {}).get("journal") or {}).get("title") or ""
        doi = normalize_doi(str(item.get("doi") or ""))
        pmcid = str(item.get("pmcid") or "")
        is_oa = str(item.get("isOpenAccess") or "").upper() == "Y"
        # No `pdf_url` is constructed for this channel. The form that used to be built here
        # (`fulltextRepo?pprId=PMC…`) answers HTTP 403 for every article, old and new, and
        # so does `pmcid=` and the API's own `?pdf=render` link: europepmc.org sits behind a
        # browser gate that returned 403 even to a browser User-Agent in testing. Claiming a
        # machine-fetchable PDF would be false and would make `_fetch_pdf` spend a candidate
        # proving it. The links the API *declares* are kept as information instead, so a
        # human or browser-capable tooling can follow them — "report the gate, do not fight
        # it", which is this project's rule for challenged sources.
        pdf_url = ""
        declared: list[dict[str, str]] = []
        for entry in (item.get("fullTextUrlList") or {}).get("fullTextUrl") or []:
            if not isinstance(entry, dict):
                continue
            url = str(entry.get("url") or "")
            if not url:
                continue
            declared.append(
                {
                    "availability": str(entry.get("availabilityCode") or ""),
                    "style": str(entry.get("documentStyle") or ""),
                    "site": str(entry.get("site") or ""),
                    "url": url,
                }
            )
        return ChannelRecord(
            channel=self.name,
            title=title,
            authors=author_list,
            year=year,
            venue=journal,
            venue_type=str(item.get("pubType") or ""),
            abstract=strip_latex(str(item.get("abstractText") or "")).replace("<h4>", " ").strip(),
            doi=doi,
            pmid=str(item.get("pmid") or ""),
            url=(
                f"https://europepmc.org/article/{item.get('source', 'MED')}/{item.get('id', '')}"
                if item.get("id")
                else (f"https://doi.org/{doi}" if doi else "")
            ),
            pdf_url=pdf_url,
            oa_status="gold" if is_oa else "",
            license=str(item.get("license") or ""),
            language=str(item.get("language") or ""),
            volume=str((item.get("journalInfo") or {}).get("volume") or ""),
            issue=str((item.get("journalInfo") or {}).get("issue") or ""),
            pages=str(item.get("pageInfo") or ""),
            kind="journal" if item.get("source") != "PPR" else "preprint",
            ev=ev_id,
            extras={
                "pmcid": pmcid,
                "source": item.get("source"),
                "is_open_access": is_oa,
                "has_full_text": str(item.get("hasTextMinedTerms") or "") == "Y"
                or str(item.get("inEPMC") or "") == "Y",
                "cited_by_count": item.get("citedByCount"),
                # Declared, not fetched: see the note above about the browser gate.
                "fulltext_urls": declared[:6],
            },
        )
