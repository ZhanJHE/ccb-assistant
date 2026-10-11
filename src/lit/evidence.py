"""Transitional alias: ``lit.evidence`` is ``lit.library.evidence``.

See ``lit/util.py`` for why this exists. New code should import
``lit.library.evidence``.
"""

from __future__ import annotations

import sys

from .library import evidence as _target

sys.modules[__name__] = _target
