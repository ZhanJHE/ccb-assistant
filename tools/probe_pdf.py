"""Diagnose the PDF download path end to end.

Run: python tools/probe_pdf.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ccb.net import Http, looks_like_pdf, pdf_rejection_reason  # noqa: E402

URLS = [
    "https://arxiv.org/pdf/1706.03762",
    "http://arxiv.org/pdf/1706.03762",
    "https://arxiv.org/pdf/1706.03762v7",
]

if __name__ == "__main__":
    http = Http()
    for url in URLS:
        try:
            data, resp = http.download(url)
            reason = pdf_rejection_reason(data, resp)
            print(f"{url}")
            print(f"    status={resp.status} error={resp.error!r} ctype={resp.content_type!r}")
            print(f"    bytes={len(data)} is_pdf={looks_like_pdf(data)} reason={reason!r}")
            if data[:400]:
                head = data[:200].decode("utf-8", "replace").replace("\n", " ")
                print(f"    head={head!r}")
        except Exception as exc:
            print(f"{url}\n    EXCEPTION {type(exc).__name__}: {exc}")
