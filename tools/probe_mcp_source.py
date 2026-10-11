"""A minimal MCP source server, used to verify the `kind: mcp` channel path.

This is a *test fixture*, not part of the tool: it stands in for a third-party MCP
server so that the MCP-as-a-source channel can be exercised end to end without
depending on any external service. It speaks the same newline-delimited JSON-RPC 2.0
that `lit.mcp_server` does, and returns one fixed paper.

    python tools/probe_mcp_source.py        # then drive it via a channels.yaml
"""

from __future__ import annotations

import json
import sys

PAPER = {
    "title": "Scaling Laws for Neural Language Models",
    "authors": ["Jared Kaplan", "Sam McCandlish", "Tom Henighan"],
    "year": 2020,
    "venue": "arXiv",
    "abstract": "We study empirical scaling laws for language model performance.",
    "doi": "",
    "arxiv_id": "2001.08361",
    "url": "https://arxiv.org/abs/2001.08361",
    "pdf_url": "https://arxiv.org/pdf/2001.08361",
}


def _reply(msg_id: object, result: dict) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}) + "\n"


def main() -> int:
    for raw in sys.stdin:
        line = (raw or "").strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        msg_id = msg.get("id")
        if method == "initialize":
            sys.stdout.write(
                _reply(
                    msg_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "probe-source", "version": "0.0.1"},
                    },
                )
            )
        elif method == "tools/list":
            sys.stdout.write(
                _reply(
                    msg_id,
                    {
                        "tools": [
                            {
                                "name": "search_papers",
                                "description": "Search a tiny fixed corpus.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {"type": "string"},
                                        "limit": {"type": "integer"},
                                    },
                                    "required": ["query"],
                                },
                            }
                        ]
                    },
                )
            )
        elif method == "tools/call":
            # Return a payload shaped like the envelope real paper MCP servers use.
            sys.stdout.write(_reply(msg_id, {"content": [{"type": "text", "text": json.dumps({"papers": [PAPER]})}]}))
        elif msg_id is not None:
            sys.stdout.write(
                json.dumps(
                    {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": method}}
                )
                + "\n"
            )
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
