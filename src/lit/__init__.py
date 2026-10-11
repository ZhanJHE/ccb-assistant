"""lit — a source-agnostic paper acquisition and local-library tool for AI harnesses.

Two layers, one entry point:

* **L1 channels** unify every way of finding or fetching a paper — free APIs, keyed
  APIs, MCP servers, local CLI tools and hand-supplied files — behind one interface.
  A channel that is gated or missing a credential degrades and says so; it never
  turns into an empty result.
* **L2 library** is a durable local corpus with stable identities, cross-source
  deduplication, field-level provenance and raw evidence snapshots, so the same paper
  is never searched, downloaded and parsed twice.

The library is plain text on disk (``works/*.json``) with a disposable SQLite index;
``Library.save`` is the single write path, and every command self-checks before it
reads, so an agent that skips a step cannot desynchronise the store.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .library import Library, default_library_root
from .model import ChannelRecord, Manifestation, WorkRecord
from .util import utc_now

__all__ = [
    "ChannelRecord",
    "Library",
    "Manifestation",
    "WorkRecord",
    "__version__",
    "default_library_root",
    "utc_now",
]
