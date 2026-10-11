#!/usr/bin/env python
"""Skill-local entry point for the `lit` tool.

The agent skill bundles a *launcher* rather than a copy of the source, so the skill
and the implementation cannot drift apart. It resolves the repository root from
``$LIT_REPO``, then from a checkout placed next to the skill directory, and finally
from a bundled ``src/`` copy.

    python tools/lit-skill.py channels
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _candidates() -> list[Path]:
    out: list[Path] = []
    env = os.environ.get("LIT_REPO", "").strip()
    if env:
        out.append(Path(env).expanduser())
    # A bundled copy inside the skill directory (self-contained installation).
    out.append(HERE.parent)
    # Sibling of the skill directory, for a checkout laid out side by side.
    out.append(HERE.parent.parent)
    out.append(Path.cwd())
    return out


def _find_src() -> Path | None:
    for base in _candidates():
        src = base / "src"
        if (src / "lit" / "cli.py").exists():
            return src
    return None


def main() -> int:
    # Windows consoles default to GBK; any paper title with accents, maths or CJK would
    # otherwise raise UnicodeEncodeError on output.
    if os.name == "nt":
        os.environ.setdefault("PYTHONUTF8", "1")
        for stream in ("stdout", "stderr"):
            s = getattr(sys, stream, None)
            if s is not None and hasattr(s, "reconfigure"):
                try:
                    s.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass

    src = _find_src()
    if src is None:
        sys.stderr.write(
            "lit: could not locate the implementation. Set LIT_REPO to the checkout "
            "root (the directory containing src/lit/), or install the package with "
            "`pip install -e .`\n"
        )
        return 5
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from lit.cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
