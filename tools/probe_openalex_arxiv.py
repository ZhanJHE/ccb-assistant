"""Probe how OpenAlex can (and cannot) resolve an arXiv identifier.

Run directly: python tools/probe_openalex_arxiv.py
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

UA = {"User-Agent": "ccb/0.1 (mailto:ccb-tool@example.org)"}


def probe(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        count = (d.get("meta") or {}).get("count")
        results = d.get("results") or []
        first = results[0].get("title", "")[:60] if results else None
        return f"200 count={count} first={first!r}"
    except urllib.error.HTTPError as e:
        return f"{e.code} " + e.read().decode("utf-8", "replace")[:180]


CASES = [
    ("A filter=ids.arxiv", "https://api.openalex.org/works?filter=ids.arxiv:1706.03762"),
    ("B filter=doi(arxiv doi)", "https://api.openalex.org/works?filter=doi:10.48550/arxiv.1706.03762"),
    ("C search=arxiv doi", "https://api.openalex.org/works?search=10.48550/arxiv.1706.03762"),
    ("D search=arxiv id", "https://api.openalex.org/works?search=1706.03762"),
    ("E filter=title.search", "https://api.openalex.org/works?filter=title.search:attention%20is%20all%20you%20need"),
    ("F filter=openalex id", "https://api.openalex.org/works/W2963403868"),
]

if __name__ == "__main__":
    for label, url in CASES:
        print(f"{label:26}: {probe(url)}")
