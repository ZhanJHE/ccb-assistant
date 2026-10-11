"""Transitional alias: ``lit.resolver`` is ``lit.search.acquire``.

See ``lit/util.py`` for why this exists. New code should import ``lit.search.acquire``
(or, more usually, ``from lit.search import Resolver``).
"""

from __future__ import annotations

import sys

from .search import acquire as _target

sys.modules[__name__] = _target
