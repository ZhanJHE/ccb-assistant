"""Transitional alias: ``lit.extract`` is ``lit.core.extract``.

See ``lit/util.py`` for why this exists. New code should import ``lit.core.extract``.
"""

from __future__ import annotations

import sys

from .core import extract as _target

sys.modules[__name__] = _target
