"""Transitional alias: ``lit.passages`` is ``lit.library.passages``.

See ``lit/util.py`` for why this exists. New code should import
``lit.library.passages``.
"""

from __future__ import annotations

import sys

from .library import passages as _target

sys.modules[__name__] = _target
