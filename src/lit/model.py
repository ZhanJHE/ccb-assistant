"""Transitional alias: ``lit.model`` is ``lit.core.model``.

See ``lit/util.py`` for why this exists. New code should import ``lit.core.model``.
"""

from __future__ import annotations

import sys

from .core import model as _target

sys.modules[__name__] = _target
