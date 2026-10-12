"""Where the running code lives — and therefore where the user's workspace is.

This module answers the one question the rest of the codebase must not guess at:
**is this a clone, and if so, where is its root?**

It matters because that answer decides where the library lives. Resolving the
library from the working directory instead made the corpus follow whoever called
the command — the harness's cwd rather than the checkout — so a tool whose whole
premise is "clone it and use it" wrote its papers somewhere other than the
directory the user cloned. A clone is the one location that is both visible and
stable; that is where the data belongs.

Standard library only, no state, and no imports from ``ccb`` itself: this is the
shared floor, and it stays there.
"""

from __future__ import annotations

from pathlib import Path

# What a checkout looks like from the inside. Both markers are required: `ccb.py`
# is the no-install entry point the repository ships, and `src/ccb/cli.py` is the
# package itself. A site-packages install has the second but never the first, and
# no ancestor of one has either — which is what keeps the cwd fallback honest
# rather than surprising.
CHECKOUT_MARKERS = ("ccb.py", "src/ccb/cli.py")


def looks_like_checkout(path: Path) -> bool:
    """True when ``path`` is the root of a clone of this repository."""
    return all((path / marker).exists() for marker in CHECKOUT_MARKERS)


def checkout_root(start: Path | str | None = None) -> Path | None:
    """The clone directory the running code sits in, or ``None`` if there is none.

    ``start`` may be a file or a directory inside the checkout; it defaults to this
    module's own location, which is what makes the answer independent of the
    working directory. Returns ``None`` for an installed package, so callers can
    fall back deliberately instead of silently writing into ``site-packages``.
    """
    here = Path(start) if start is not None else Path(__file__)
    try:
        here = here.resolve()
    except OSError:  # pragma: no cover - unreadable path, treated as "not a clone"
        return None
    for base in (here, *here.parents):
        if looks_like_checkout(base):
            return base
    return None


__all__ = ["CHECKOUT_MARKERS", "checkout_root", "looks_like_checkout"]
