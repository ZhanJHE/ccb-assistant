"""ccb — three modules over one shared floor, for AI harnesses.

* **core** is the shared floor: the canonical records, the ``work_id`` key chain,
  text normalisation and PDF extraction. It imports none of the other modules.
* **library** keeps the durable local corpus — stable identities, cross-source
  deduplication, field-level provenance and raw evidence snapshots — so the same
  paper is never searched, downloaded and parsed twice. It performs no network I/O.
* **search** unifies every way of finding or fetching a paper — free APIs, keyed
  APIs, MCP servers, local CLI tools and hand-supplied files — behind one interface.
  A channel that is gated or missing a credential degrades and says so; it never
  turns into an empty result. It is the only writer to the corpus.
* **topics** mines that corpus for one research topic at a time, returning anchored
  evidence, a section skeleton and a CCF estimate with its basis. It writes no prose.

A module may import only what is listed beneath it; ``tests/test_modules.py`` parses
the real import graph and fails if that is violated.

The corpus is plain text on disk (``works/*.json``) with a disposable SQLite index;
``Library.save`` is the single write path, and every command self-checks before it
reads, so an agent that skips a step cannot desynchronise the store.
"""

from __future__ import annotations

__version__ = "0.5.0"

from .core.model import ChannelRecord, Manifestation, WorkRecord
from .core.util import utc_now
from .library import Library, default_library_root

__all__ = [
    "ChannelRecord",
    "Library",
    "Manifestation",
    "WorkRecord",
    "__version__",
    "default_library_root",
    "utc_now",
]
