"""Transitional alias: ``lit.ids`` is ``lit.core.ids``.

See ``lit/util.py`` for why this exists. New code should import ``lit.core.ids``.
"""

from __future__ import annotations

import sys

from .core import ids as _target

sys.modules[__name__] = _target
