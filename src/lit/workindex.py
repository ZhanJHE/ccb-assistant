"""Transitional alias: ``lit.workindex`` is ``lit.library.index``.

See ``lit/util.py`` for why this exists. New code should import ``lit.library.index``.
"""

from __future__ import annotations

import sys

from .library import index as _target

sys.modules[__name__] = _target
