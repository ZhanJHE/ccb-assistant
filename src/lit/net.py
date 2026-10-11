"""Transitional alias: ``lit.net`` is ``lit.search.net``.

See ``lit/util.py`` for why this exists. New code should import ``lit.search.net``.
"""

from __future__ import annotations

import sys

from .search import net as _target

sys.modules[__name__] = _target
