"""Transitional alias: ``lit.cite`` is ``lit.library.cite``.

See ``lit/util.py`` for why this exists. New code should import ``lit.library.cite``.
"""

from __future__ import annotations

import sys

from .library import cite as _target

sys.modules[__name__] = _target
