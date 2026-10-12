#!/usr/bin/env python
"""Run the ccb CLI from a checkout, with no install step.

    python ccb.py channels
    python ccb.py find "graph neural networks" -n 5

Keeping this at the repository root means the tool is usable immediately after a
clone, which matters when an agent needs to call it from a harness that has not
installed anything.

The library lives at ``<checkout>/papers``, next to this file: it is resolved from the
checkout rather than the working directory, so the papers land in the directory you
cloned no matter where the command is run from. ``--library`` or ``$CCB_HOME`` override
it. That directory is local data and is not version controlled.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Force UTF-8 stdio: on Windows the default code page is GBK and any paper title with
# accents, maths symbols or CJK otherwise raises UnicodeEncodeError on output.
if os.name == "nt":
    os.environ.setdefault("PYTHONUTF8", "1")
    for stream in ("stdout", "stderr"):
        s = getattr(sys, stream, None)
        if s is not None and hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ccb.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
