"""Transitional alias: ``lit.util`` is ``lit.core.util``.

The module moved into the ``core`` package when lit was split into three business
modules (search / library / topics) over a shared floor. This alias registers the
*identical* module object under the old name, so the two paths can never drift.
New code should import ``lit.core.util``; delete this file once callers have moved.
"""

from __future__ import annotations

import sys

from .core import util as _target

sys.modules[__name__] = _target
