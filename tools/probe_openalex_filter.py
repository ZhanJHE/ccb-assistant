"""Inspect exactly what OpenAlex returns for the arXiv-DOI filter.

Run: python tools/probe_openalex_filter.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lit.channels.openalex import OpenAlexChannel  # noqa: E402
from lit.net import Http  # noqa: E402

UA = {"User-Agent": "lit/0.1 (mailto:lit-tool@example.org)"}


def raw(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"_status": e.code, "_body": e.read().decode("utf-8", "replace")[:300]}


if __name__ == "__main__":
    url = ("https://api.openalex.org/works?filter=doi:10.48550/arxiv.1706.03762"
           "&select=id,doi,title,publication_year,type,primary_location")
    d = raw(url)
    print("RAW filter=doi:10.48550/arxiv.1706.03762")
    print(f"  meta  = {d.get('meta')}")
    for w in (d.get("results") or [])[:3]:
        loc = ((w.get("primary_location") or {}).get("source") or {})
        print(f"  id={w.get('id')} doi={w.get('doi')!r} year={w.get('publication_year')}")
        print(f"     title={w.get('title')!r}")
        print(f"     source={loc.get('display_name')!r}")

    print()
    print("--- via the channel class (as the resolver sees it) ---")
    ch = OpenAlexChannel(http=Http())
    res = ch.lookup("arxiv:1706.03762")
    print(f"  error={res.error!r} records={len(res.records)}")
    print(f"  queries={res.queries}")
    for rec in res.records:
        print(f"     doi={rec.doi!r} title={rec.title[:70]!r} venue={rec.venue!r}")
