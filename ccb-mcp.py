#!/usr/bin/env python
"""Run the ccb MCP server from a checkout, with no install step.

    python ccb-mcp.py                             # serve over stdio
    python ccb-mcp.py --list-tools                # inspect the exposed tools
    python ccb-mcp.py --library ./other-papers    # point at another corpus

Registering it with an MCP client is then just a command entry. For example, a client
that takes a JSON config:

    {
      "mcpServers": {
        "ccb": {
          "command": "python",
          "args": ["C:/path/to/ccb-assistant/ccb-mcp.py"]
        }
      }
    }

The library defaults to ``<checkout>/papers``, so omit ``--library`` to use the corpus in
this directory; pass it (or set ``CCB_HOME``) to point at another one.

The server exposes the same behaviour as the CLI because both are adapters onto one
core — there is no MCP-specific logic to drift.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# UTF-8 stdio: JSON-RPC over a Windows console otherwise mangles non-ASCII titles and
# can corrupt the framing.
if os.name == "nt":
    os.environ.setdefault("PYTHONUTF8", "1")
    for stream in ("stdin", "stdout"):
        handle = getattr(sys, stream, None)
        if handle is not None and hasattr(handle, "reconfigure"):
            try:
                handle.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ccb.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
