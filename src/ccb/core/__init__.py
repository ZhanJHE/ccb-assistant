"""The shared floor: records, identities, normalisation and PDF extraction.

Nothing here knows about the network and nothing here knows about the library on
disk. That is the point: ``core`` is the only package the two business modules can
both import, so it must stay free of state and free of dependencies. If a helper in
here ever needs to reach for a channel or a work file, it belongs in one of the
modules instead.
"""

from __future__ import annotations

from .ids import compute_work_id, parse_identifier, work_path_shard
from .model import ChannelRecord, Manifestation, WorkRecord
from .util import normalize_doi, normalize_title, utc_now

__all__ = [
    "ChannelRecord",
    "Manifestation",
    "WorkRecord",
    "compute_work_id",
    "normalize_doi",
    "normalize_title",
    "parse_identifier",
    "utc_now",
    "work_path_shard",
]
