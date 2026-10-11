"""Reproduce the arXiv channel's lookup and search behaviour, with full detail.

Run: python tools/probe_arxiv.py
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lit.channels.arxiv import ArxivChannel  # noqa: E402
from lit.net import Http  # noqa: E402


def show(label: str, chan: ArxivChannel, fn, *args, **kw) -> None:
    print(f"--- {label}")
    try:
        res = fn(*args, **kw)
    except Exception:
        traceback.print_exc()
        return
    print(f"    error   : {res.error!r}")
    print(f"    records : {len(res.records)}")
    print(f"    warnings: {res.warnings}")
    print(f"    queries : {res.queries}")
    for rec in res.records[:3]:
        print(f"      -> arxiv_id={rec.arxiv_id!r} doi={rec.doi!r} pdf={rec.pdf_url!r}")
        print(f"         title={rec.title[:70]!r}")


if __name__ == "__main__":
    chan = ArxivChannel(http=Http(host_rates={"export.arxiv.org": 0.34}))
    show("lookup('arxiv:1706.03762')", chan, chan.lookup, "arxiv:1706.03762")
    show("lookup('1706.03762')", chan, chan.lookup, "1706.03762")
    show("lookup('http://arxiv.org/abs/1706.03762v7')", chan, chan.lookup,
         "http://arxiv.org/abs/1706.03762v7")
    show("search('attention is all you need', limit=2)", chan, chan.search,
         "attention is all you need", limit=2)
