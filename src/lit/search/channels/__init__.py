"""Channel implementations and the registry that routes between them."""

from __future__ import annotations

from .base import (
    CAP_BIBTEX,
    CAP_CITATIONS,
    CAP_FULLTEXT,
    CAP_LOOKUP,
    CAP_OA_RESOLVE,
    CAP_PDF,
    CAP_SEARCH,
    CAP_VENUE,
    Channel,
    ChannelResult,
    ChannelSpec,
    ManualChannel,
)
from .registry import BUILTIN_CHANNELS, KNOWN_HEALTH, Registry

__all__ = [
    "BUILTIN_CHANNELS",
    "CAP_BIBTEX",
    "CAP_CITATIONS",
    "CAP_FULLTEXT",
    "CAP_LOOKUP",
    "CAP_OA_RESOLVE",
    "CAP_PDF",
    "CAP_SEARCH",
    "CAP_VENUE",
    "Channel",
    "ChannelResult",
    "ChannelSpec",
    "KNOWN_HEALTH",
    "ManualChannel",
    "Registry",
]
