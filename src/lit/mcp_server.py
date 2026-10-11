"""A Model Context Protocol server over the same core the CLI drives.

The objective for this tool names three faces for one implementation: a CLI, an Agent
Skill, and MCP. This module is the MCP face. It deliberately contains **no logic** —
every tool is a thin adapter onto `Library` / `Resolver`, so an MCP client and a shell
caller cannot diverge in behaviour, identity, or safety policy.

Transport is stdio with newline-delimited JSON-RPC 2.0, implemented directly rather
than via an SDK. That keeps the tool's "no required third-party dependency" property,
which matters because the MCP face is meant to be an *option*, not a prerequisite.

Tools exposed (deliberately few, each mapping to one decision a caller must make):

  lit_contract   the operating rules and canonical step order
  lit_channels   which channels are usable, and which credential each one wants
  lit_find       search local first, then channels
  lit_get        acquire one paper by identifier, idempotently
  lit_ask        retrieve page-anchored passages that answer a question
  lit_open       stored full text, no network
  lit_cite       citation for one work, with field provenance
  lit_export     bibliography for a set of works
  lit_stats      corpus state, including pending duplicate candidates

Every tool returns the same JSON the CLI emits, so a result can be reproduced from a
shell and compared.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from . import __version__
from .contract import contract
from .library import Library, default_library_root
from .library.cite import export as cite_export
from .library.cite import to_bibtex, to_csl_json, to_ris
from .search import Registry, Resolver
from .topics import commands as topics_commands

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "lit"
SERVER_VERSION = __version__

# JSON-RPC error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


# --------------------------------------------------------------------------- #
# Tool schemas
# --------------------------------------------------------------------------- #

def tool_definitions() -> list[dict[str, Any]]:
    """The advertised tool list. Descriptions state when to use each one."""
    return [
        {
            "name": "lit_contract",
            "description": (
                "Return the operating rules, invariants and canonical step order for this "
                "tool. Call this first if you are unsure how to proceed, or after an "
                "unexpected result."
            ),
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "lit_channels",
            "description": (
                "List every paper source (channel) with its availability, capabilities and "
                "the name of any credential it is missing. Credential values are never "
                "returned."
            ),
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "lit_find",
            "description": (
                "Find papers on a topic. Queries the local library first and only fans out "
                "to channels on a miss, storing what it finds so the same paper is never "
                "searched for twice."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Topic or keywords."},
                    "limit": {"type": "integer", "default": 10},
                    "sources": {
                        "type": "string",
                        "description": "Channel selector: 'auto' (default), 'all', or a comma-separated list.",
                    },
                    "year_from": {"type": "integer"},
                    "year_to": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
        {
            "name": "lit_get",
            "description": (
                "Acquire one paper by identifier (DOI, arXiv id, OpenReview id, dblp key, "
                "PMID, URL or an existing work_id). Resolves locally first; re-running on a "
                "paper already held costs nothing."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "identifier": {"type": "string"},
                    "with_pdf": {
                        "type": "boolean",
                        "default": False,
                        "description": "Download the open-access PDF and extract its text.",
                    },
                    "refresh": {
                        "type": "boolean",
                        "default": False,
                        "description": "Re-query the channels even if the paper is already local.",
                    },
                },
                "required": ["identifier"],
            },
        },
        {
            "name": "lit_ask",
            "description": (
                "Answer a question from the local corpus. Returns ranked passages with "
                "work_id and page anchors instead of prose, so any claim can be verified. "
                "Compose the answer yourself and cite the returned anchors. If 'grounded' is "
                "false, say the corpus does not cover the question rather than answering "
                "from memory."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                    "work_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Restrict to these works (default: whole corpus).",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "lit_open",
            "description": "Read a paper's stored full text. Never touches the network.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "identifier": {"type": "string"},
                    "head": {
                        "type": "integer",
                        "default": 20000,
                        "description": "Maximum characters to return.",
                    },
                },
                "required": ["identifier"],
            },
        },
        {
            "name": "lit_cite",
            "description": (
                "Citation for one work in BibTeX, RIS, CSL-JSON or plain text, together with "
                "which source supplied each field and which fields no source provided."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "identifier": {"type": "string"},
                    "format": {
                        "type": "string",
                        "enum": ["bibtex", "ris", "csl", "text"],
                        "default": "bibtex",
                    },
                },
                "required": ["identifier"],
            },
        },
        {
            "name": "lit_export",
            "description": "Bibliography for several works at once.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "format": {"type": "string", "default": "bibtex"},
                    "work_ids": {"type": "array", "items": {"type": "string"}},
                    "query": {"type": "string", "description": "Substring filter over title/abstract."},
                },
                "required": [],
            },
        },
        {
            "name": "lit_stats",
            "description": (
                "Corpus state: how many works, how many with PDFs and full text, evidence "
                "snapshots, and duplicate candidates awaiting a decision."
            ),
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "lit_topics_survey",
            "description": (
                "Step 1 of topic generation. Map what the local corpus holds for a "
                "direction: works, years, venues with CCF ranks, terms. Tops the direction "
                "up from the channels when it is too thin to mine, and reports what it "
                "added. Returns sufficient=false when there is still too little evidence."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The direction to mine."},
                    "min_works": {"type": "integer", "default": 20},
                    "min_fulltext": {"type": "integer", "default": 5},
                    "year_from": {"type": "integer"},
                    "year_to": {"type": "integer"},
                    "limit": {"type": "integer", "default": 200},
                    "top_terms": {"type": "integer", "default": 40},
                    "max_n": {"type": "integer", "default": 2, "description": "Longest term phrase (1-3)."},
                    "offline": {
                        "type": "boolean",
                        "default": False,
                        "description": "Do not top the direction up from channels.",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "lit_topics_gaps",
            "description": (
                "Step 2. The gap evidence for a survey: sentences where authors state "
                "limitations or future work (with work_id and page), sparse term pairs, "
                "and a tally by gap kind. This is evidence to read, not a conclusion."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "survey_id": {"type": "string"},
                    "limit": {"type": "integer", "default": 60},
                    "max_per_work": {"type": "integer", "default": 3},
                },
                "required": ["survey_id"],
            },
        },
        {
            "name": "lit_topics_candidates",
            "description": (
                "Step 3. Ranked (evidence x novelty operator) topic candidates, with a "
                "score whose four parts are reported, and the local works that share each "
                "candidate's terms. Combinations already committed are excluded, which is "
                "what makes repeated mining non-repetitive."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "survey_id": {"type": "string"},
                    "limit": {"type": "integer", "default": 25},
                    "per_kind": {"type": "integer", "default": 15},
                    "include_mined": {"type": "boolean", "default": False},
                    "no_self_check": {"type": "boolean", "default": False},
                },
                "required": ["survey_id"],
            },
        },
        {
            "name": "lit_topics_draft",
            "description": (
                "Step 4. Commit to ONE candidate. Returns the section skeleton a paper of "
                "this kind needs — background, the four-step gap derivation, research "
                "questions, contributions, approach, expected experiments and datasets, "
                "anticipated criticism, references — with every claim's anchor attached. "
                "The tool does not write prose; compose each section from its anchors."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"candidate_id": {"type": "string"}},
                "required": ["candidate_id"],
            },
        },
        {
            "name": "lit_topics_rate",
            "description": (
                "Step 5. The CCF estimate for a topic: upper bound, band, confidence, and "
                "the basis for every movement with its reason. A rule-based estimate from "
                "the recorded evidence, not an acceptance prediction. Name a target venue "
                "to check the estimate against that venue's own catalogue rank."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string"},
                    "venue": {"type": "string", "description": "Optional target venue."},
                },
                "required": ["topic_id"],
            },
        },
        {
            "name": "lit_topics_save",
            "description": (
                "Step 6. Commit a topic: export the Markdown draft and retire its "
                "de-duplication keys so the same combination is never proposed again."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"topic_id": {"type": "string"}},
                "required": ["topic_id"],
            },
        },
        {
            "name": "lit_topics_list",
            "description": "Topics already mined, newest first, with what each consumed.",
            "inputSchema": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 0}},
                "required": [],
            },
        },
    ]


# --------------------------------------------------------------------------- #
# Server
# --------------------------------------------------------------------------- #


class McpServer:
    """Routes MCP tool calls onto the library and resolver."""

    def __init__(self, library_root: Path | str | None = None, *, verbose: bool = False):
        root = Path(library_root) if library_root else default_library_root()
        self.library = Library(root)
        self.library.ensure()
        self.registry = Registry(evidence=self.library.evidence, verbose=verbose)
        self.resolver = Resolver(self.library, self.registry, verbose=verbose)

    # ---------------- tool implementations ---------------- #

    def _tool_contract(self, args: dict[str, Any]) -> dict[str, Any]:
        return contract()

    def _tool_channels(self, args: dict[str, Any]) -> dict[str, Any]:
        summary = self.registry.availability_summary()
        out: dict[str, Any] = {
            "channels": self.registry.report(),
            "usable": summary["usable"],
            "unavailable": summary["unavailable"],
            "credentials_present": summary["credentials_present"],
        }
        # A credential whose channel is not loaded is a silent misconfiguration; pass it
        # through the same way the CLI does so both faces report it.
        for key in ("credentials_without_channel", "credentials_without_channel_note"):
            if key in summary:
                out[key] = summary[key]
        return out

    def _tool_find(self, args: dict[str, Any]) -> dict[str, Any]:
        res = self.resolver.find(
            _require_str(args, "query"),
            limit=int(args.get("limit") or 10),
            channels=str(args.get("sources") or ""),
            year_from=_opt_int(args.get("year_from")),
            year_to=_opt_int(args.get("year_to")),
        )
        return res.as_dict()

    def _tool_get(self, args: dict[str, Any]) -> dict[str, Any]:
        res = self.resolver.get(
            _require_str(args, "identifier"),
            with_pdf=bool(args.get("with_pdf")),
            refresh=bool(args.get("refresh")),
            # Match the CLI: downloading a PDF implies making it readable.
            extract=bool(args.get("with_pdf")),
        )
        return res.as_dict()

    def _tool_ask(self, args: dict[str, Any]) -> dict[str, Any]:
        ids = args.get("work_ids")
        return self.resolver.ask(
            _require_str(args, "query"),
            limit=int(args.get("limit") or 5),
            work_ids=[str(i) for i in ids] if isinstance(ids, list) and ids else None,
        )

    def _tool_open(self, args: dict[str, Any]) -> dict[str, Any]:
        work = self.library.resolve(_require_str(args, "identifier"))
        if work is None:
            return _error(
                "not_found",
                "not in the local library; call lit_get first",
            )
        text = self.library.read_fulltext(work)
        if not text:
            return _error(
                "no_fulltext",
                "no extracted text stored for this work; call lit_get with with_pdf=true",
                work_id=work.work_id,
                has_pdf=work.has_pdf(),
            )
        head = int(args.get("head") or 20000)
        total = len(text)
        return {
            "work_id": work.work_id,
            "title": work.title(),
            "chars": len(text[:head]),
            "total_chars": total,
            "truncated": head < total,
            "text": text[:head],
        }

    def _tool_cite(self, args: dict[str, Any]) -> dict[str, Any]:
        work = self.library.resolve(_require_str(args, "identifier"))
        if work is None:
            return _error("not_found", "not in the local library; call lit_get first")
        fmt = str(args.get("format") or "bibtex").casefold()
        if fmt in ("bibtex", "bib"):
            rendered = to_bibtex(work)
        elif fmt == "ris":
            rendered = to_ris(work)
        elif fmt in ("csl", "json"):
            rendered = json.dumps(to_csl_json(work), ensure_ascii=False, indent=2)
        else:
            from .library.cite import _plain

            rendered = _plain(work)
        return {
            "work_id": work.work_id,
            "format": fmt,
            "citation": rendered,
            "provenance": {
                f: [c.src for c in work.claims.get(f, [])]
                for f in ("title", "authors", "year", "venue", "doi", "pages", "volume")
                if work.claims.get(f)
            },
            "unavailable_fields": [
                f for f in ("title", "authors", "year", "venue", "doi") if not work.claims.get(f)
            ],
        }

    def _tool_export(self, args: dict[str, Any]) -> dict[str, Any]:
        ids = args.get("work_ids")
        works = []
        missing: list[str] = []
        if isinstance(ids, list) and ids:
            for wid in ids:
                w = self.library.resolve(str(wid))
                if w is None:
                    missing.append(str(wid))
                else:
                    works.append(w)
        else:
            works = list(self.library.iter_works())
        needle = str(args.get("query") or "").casefold()
        if needle:
            works = [w for w in works if needle in (w.title() + " " + w.abstract()).casefold()]
        fmt = str(args.get("format") or "bibtex")
        out: dict[str, Any] = {"format": fmt, "entries": len(works),
                               "text": cite_export(works, fmt=fmt)}
        if missing:
            out["not_found"] = missing
        return out

    def _tool_stats(self, args: dict[str, Any]) -> dict[str, Any]:
        stats = self.library.stats()
        stats["pending_merges"] = self.library.unresolved_merges()
        return stats

    # ---------------- module three: topic generation ---------------- #
    #
    # Topic generation is a long process with judgement in the middle, so it is exposed
    # as several steps rather than one tool: the agent has to be able to read the gap
    # evidence before choosing, and to pick a single candidate before drafting.

    def _tool_topics_survey(self, args: dict[str, Any]) -> dict[str, Any]:
        return topics_commands.run(
            "survey",
            self.library,
            None if args.get("offline") else self.resolver,
            SimpleNamespace(
                query=_require_str(args, "query"),
                min_works=_opt_int(args.get("min_works")),
                min_fulltext=_opt_int(args.get("min_fulltext")),
                year_from=_opt_int(args.get("year_from")),
                year_to=_opt_int(args.get("year_to")),
                limit=_opt_int(args.get("limit")),
                top_terms=_opt_int(args.get("top_terms")),
                max_n=_opt_int(args.get("max_n")),
                offline=bool(args.get("offline")),
            ),
        )

    def _tool_topics_gaps(self, args: dict[str, Any]) -> dict[str, Any]:
        return topics_commands.run(
            "gaps",
            self.library,
            self.resolver,
            SimpleNamespace(
                survey_id=_require_str(args, "survey_id"),
                limit=_opt_int(args.get("limit")),
                max_per_work=_opt_int(args.get("max_per_work")),
            ),
        )

    def _tool_topics_candidates(self, args: dict[str, Any]) -> dict[str, Any]:
        return topics_commands.run(
            "candidates",
            self.library,
            self.resolver,
            SimpleNamespace(
                survey_id=_require_str(args, "survey_id"),
                limit=_opt_int(args.get("limit")),
                per_kind=_opt_int(args.get("per_kind")),
                include_mined=bool(args.get("include_mined")),
                no_self_check=bool(args.get("no_self_check")),
            ),
        )

    def _tool_topics_draft(self, args: dict[str, Any]) -> dict[str, Any]:
        return topics_commands.run(
            "draft",
            self.library,
            self.resolver,
            SimpleNamespace(candidate_id=_require_str(args, "candidate_id")),
        )

    def _tool_topics_rate(self, args: dict[str, Any]) -> dict[str, Any]:
        return topics_commands.run(
            "rate",
            self.library,
            self.resolver,
            SimpleNamespace(
                topic_id=_require_str(args, "topic_id"),
                venue=str(args.get("venue") or ""),
            ),
        )

    def _tool_topics_save(self, args: dict[str, Any]) -> dict[str, Any]:
        return topics_commands.run(
            "save",
            self.library,
            self.resolver,
            SimpleNamespace(topic_id=_require_str(args, "topic_id")),
        )

    def _tool_topics_list(self, args: dict[str, Any]) -> dict[str, Any]:
        return topics_commands.run(
            "list",
            self.library,
            self.resolver,
            SimpleNamespace(limit=_opt_int(args.get("limit"))),
        )

    def call_tool(self, name: str, args: dict[str, Any] | None) -> dict[str, Any]:
        handler: Callable[[dict[str, Any]], dict[str, Any]] | None = getattr(
            self, f"_tool_{name.removeprefix('lit_')}", None
        )
        if handler is None:
            raise McpToolError(f"unknown tool {name!r}", METHOD_NOT_FOUND)
        return handler(args or {})

    def close(self) -> None:
        self.library.close()


class McpToolError(Exception):
    def __init__(self, message: str, code: int = INTERNAL_ERROR):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- #
# Protocol plumbing
# --------------------------------------------------------------------------- #


def _require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise McpToolError(f"missing required string parameter {key!r}", INVALID_PARAMS)
    return value.strip()


def _opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _error(kind: str, message: str, **extra: Any) -> dict[str, Any]:
    """A tool-level failure, returned as data rather than raised.

    Tool failures are reported inside the result so the caller can read the reason and
    adapt, instead of seeing an opaque JSON-RPC error it cannot act on.
    """
    return {"ok": False, "error": kind, "message": message, **extra}


def _handle_protocol(msg: dict[str, Any], server: McpServer) -> dict[str, Any] | None:
    """Handle one JSON-RPC message. Returns None for notifications."""
    msg_id = msg.get("id")
    method = msg.get("method", "")
    is_notification = msg_id is None

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }
        return None if is_notification else _result(msg_id, result)

    if method in ("notifications/initialized", "initialized"):
        return None

    if method == "tools/list":
        return None if is_notification else _result(msg_id, {"tools": tool_definitions()})

    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            payload = server.call_tool(name, args)
        except McpToolError as exc:
            return None if is_notification else _error_response(msg_id, exc.code, str(exc))
        except Exception as exc:  # a tool bug must not kill the session
            return (
                None
                if is_notification
                else _error_response(msg_id, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")
            )
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        # MCP tool results are content blocks; the structured payload travels as text so
        # it survives clients that do not surface structuredContent.
        return (
            None
            if is_notification
            else _result(msg_id, {"content": [{"type": "text", "text": text}]})
        )

    if method == "ping":
        return None if is_notification else _result(msg_id, {})

    if is_notification:
        return None
    return _error_response(msg_id, METHOD_NOT_FOUND, f"unknown method {method!r}")


def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error_response(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def serve(
    *,
    library_root: Path | str | None = None,
    stdin: Any = None,
    stdout: Any = None,
    verbose: bool = False,
) -> int:
    """Serve MCP over stdio until stdin closes. Newline-delimited JSON-RPC."""
    instream = stdin if stdin is not None else sys.stdin
    outstream = stdout if stdout is not None else sys.stdout
    server = McpServer(library_root, verbose=verbose)
    try:
        for raw in instream:
            line = (raw or "").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as exc:
                outstream.write(
                    json.dumps(_error_response(None, PARSE_ERROR, str(exc))) + "\n"
                )
                outstream.flush()
                continue
            if isinstance(msg, list):
                # A batch is answered as a batch, as the spec requires.
                responses = [
                    r for r in (_handle_protocol(m, server) for m in msg if isinstance(m, dict))
                    if r is not None
                ]
                if responses:
                    outstream.write(json.dumps(responses, ensure_ascii=False) + "\n")
                    outstream.flush()
                continue
            if not isinstance(msg, dict):
                outstream.write(
                    json.dumps(_error_response(None, INVALID_REQUEST, "message must be an object"))
                    + "\n"
                )
                outstream.flush()
                continue
            response = _handle_protocol(msg, server)
            if response is not None:
                outstream.write(json.dumps(response, ensure_ascii=False) + "\n")
                outstream.flush()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    finally:
        server.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="lit-mcp",
        description="MCP server for lit (stdio, newline-delimited JSON-RPC).",
    )
    parser.add_argument("--library", help="library root (default: $LIT_HOME or ./.lit)")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--list-tools", action="store_true", help="print the tool list and exit"
    )
    args = parser.parse_args(argv)
    if args.list_tools:
        json.dump({"tools": tool_definitions()}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    return serve(library_root=args.library, verbose=args.verbose)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
