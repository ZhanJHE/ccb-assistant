"""Transitional alias: ``lit.channels`` is ``lit.search.channels``.

The channel layer moved into the ``search`` package when lit was split into three
business modules. This alias registers the identical module object under the old
name — including every submodule, so ``lit.channels.base`` and
``lit.search.channels.base`` resolve to the *same* module rather than two independent
copies. New code should import ``lit.search.channels``; delete this package once
callers have moved.
"""

from __future__ import annotations

import importlib
import sys

from ..search import channels as _target

_SUBMODULES = (
    "arxiv",
    "base",
    "crossref",
    "dblp",
    "europepmc",
    "generic",
    "openalex",
    "openreview",
    "paper_search",
    "registry",
)

for _sub in _SUBMODULES:
    sys.modules[f"{__name__}.{_sub}"] = importlib.import_module(
        f"lit.search.channels.{_sub}"
    )

sys.modules[__name__] = _target
