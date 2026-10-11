"""The persistent paper library, and everything derived from it.

This package owns the corpus: the work records on disk, the raw evidence snapshots
they cite, the disposable SQLite index over them, the passage index used for
grounded retrieval, and citation export. It performs **no network I/O** — acquiring
papers is the ``search`` package's job, and it writes here.

``Library.save`` remains the single write path, so the record, the index and the
ledger cannot diverge no matter which module asked for the write.
"""

from __future__ import annotations

from . import cite, passages, retrieve
from .evidence import Evidence, EvidenceStore
from .index import WORK_FILE_GLOB, WorkIndex
from .store import DedupCandidate, Library, UpsertResult, default_library_root

__all__ = [
    "DedupCandidate",
    "Evidence",
    "EvidenceStore",
    "Library",
    "UpsertResult",
    "WORK_FILE_GLOB",
    "WorkIndex",
    "cite",
    "default_library_root",
    "passages",
    "retrieve",
]
