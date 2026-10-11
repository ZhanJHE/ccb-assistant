"""Search and download: every way of finding or fetching a paper, unified.

Four kinds of source are supported and are indistinguishable to a caller: ``http``
APIs, a locally installed ``cli`` tool, a third-party ``mcp`` server, and a
``manual`` file you already have. A channel that is gated, rate-limited or missing a
credential degrades and *names the reason* rather than quietly returning nothing.

This package is the only writer into the library. It depends on ``core`` and
``library``; nothing in either of those may import from here.
"""

from __future__ import annotations

from .acquire import AcquireResult, FindResult, Resolver, STOP_AFTER_LOOKUP_SUCCESS
from .channels import Registry
from .net import Http, Response, credential

__all__ = [
    "AcquireResult",
    "FindResult",
    "Http",
    "Registry",
    "Resolver",
    "Response",
    "STOP_AFTER_LOOKUP_SUCCESS",
    "credential",
]
