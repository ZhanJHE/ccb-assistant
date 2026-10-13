#!/usr/bin/env python
"""Skill-local launcher for the `ccb` tool.

The skill deliberately ships a *launcher*, not a copy of the implementation, so the
two cannot drift apart. It finds the checkout in this order:

1. ``$CCB_REPO`` (the directory containing ``src/ccb/``)
2. a bundled ``src/`` next to this file (a self-contained skill install)
3. the parent chain of this skill directory (the usual in-repo layout,
   ``<repo>/.dsh/skills/ccb/``)
4. the current working directory

    python ~/.dsh/skills/ccb/ccb.py channels
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    env = os.environ.get("CCB_REPO", "").strip()
    if env:
        roots.append(Path(env).expanduser())
    roots.append(HERE)                 # bundled src/ inside the skill
    roots.append(HERE.parent.parent)   # <repo>/.dsh/skills/ccb -> <repo>/.dsh/skills -> <repo>
    roots.append(HERE.parent)
    roots.append(Path.cwd())
    return roots


def _find_src() -> Path | None:
    for root in _candidate_roots():
        src = root / "src"
        # No suffix: `ccb/cli` is a package today and was a module once, and a marker
        # that named the file form stopped matching when the split happened.
        if (src / "ccb" / "cli").exists():
            return src
    # The package may also be installed normally.
    try:
        import ccb.cli  # noqa: F401

        return None
    except Exception:
        return None


def main() -> int:
    # Windows consoles are GBK by default; a paper title with accents, maths or CJK
    # would otherwise raise UnicodeEncodeError while printing results.
    if os.name == "nt":
        os.environ.setdefault("PYTHONUTF8", "1")
        for stream in ("stdout", "stderr"):
            handle = getattr(sys, stream, None)
            if handle is not None and hasattr(handle, "reconfigure"):
                try:
                    handle.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass

    src = _find_src()
    if src is not None and str(src) not in sys.path:
        sys.path.insert(0, str(src))

    try:
        from ccb.cli import main as cli_main
    except ImportError:
        sys.stderr.write(
            "ccb: could not locate the implementation.\n"
            "Set CCB_REPO to the checkout root (the directory containing src/ccb/), "
            "or install the package with `pip install -e .`.\n"
            f"Looked in: {', '.join(str(r) for r in _candidate_roots())}\n"
        )
        return 5

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
