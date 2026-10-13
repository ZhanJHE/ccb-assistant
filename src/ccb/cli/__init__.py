"""The CLI — the only supported way to touch the library.

Design rules, all of them there because an agent is the primary caller:

* **JSON on stdout, always.** Prose goes to stderr. `--pretty` is for humans; the
  default is compact machine-readable output.
* **Exit codes are meaningful and few.** 0 success, 2 usage error, 3 not found,
  4 partial (some channels failed but the operation produced something), 5 hard
  failure. A caller can branch on them without parsing text.
* **Failures are never silent.** A gated, rate-limited or key-less channel appears in
  an `errors` map by name with a reason. "Nothing found" and "could not look" are
  different outcomes and are reported differently.
* **Idempotent.** Re-running any command converges; nothing depends on the caller
  having run a previous command.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Sequence

from .. import __version__

from ._context import (
    EXIT_FAILED,
    EXIT_NOT_FOUND,
    EXIT_OK,
    EXIT_PARTIAL,
    EXIT_USAGE,
    CommandError,
    Context,
    _config_paths,
    _not_found,
    _split,
)
from ._handlers import (
    _compact,
    _extract_into,
    _extract_with_engine,
    _legacy_libraries,
    cmd_add_file,
    cmd_ask,
    cmd_channels,
    cmd_check,
    cmd_check_files,
    cmd_cite,
    cmd_contract,
    cmd_doctor,
    cmd_evidence,
    cmd_export,
    cmd_extract,
    cmd_find,
    cmd_get,
    cmd_index,
    cmd_ledger,
    cmd_library,
    cmd_merge,
    cmd_open,
    cmd_reindex,
    cmd_repair,
    cmd_search_local,
    cmd_show,
    cmd_topics,
)
from ._parser import build_parser
from ._render import _record_keys_for, _render_pretty

__all__ = [
    "EXIT_FAILED", "EXIT_NOT_FOUND", "EXIT_OK", "EXIT_PARTIAL", "EXIT_USAGE",
    "CommandError", "Context", "build_parser", "main",
    "cmd_add_file", "cmd_ask", "cmd_channels", "cmd_check", "cmd_check_files",
    "cmd_cite", "cmd_contract", "cmd_doctor", "cmd_evidence", "cmd_export",
    "cmd_extract", "cmd_find", "cmd_get", "cmd_index", "cmd_ledger", "cmd_library",
    "cmd_merge", "cmd_open", "cmd_reindex", "cmd_repair", "cmd_search_local",
    "cmd_show", "cmd_topics",
    "_compact", "_config_paths", "_legacy_libraries", "_not_found",
    "_record_keys_for", "_render_pretty", "_split",
]


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        ctx = Context(args)
    except Exception as exc:
        sys.stderr.write(json.dumps({"error": f"could not open the library: {exc}"}) + "\n")
        return EXIT_FAILED
    try:
        return args.func(ctx)
    except CommandError as exc:
        payload = {"error": exc.message, **exc.extra}
        if args.pretty:
            sys.stderr.write(f"error: {exc.message}\n")
        else:
            sys.stderr.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return exc.code
    except BrokenPipeError:
        return EXIT_OK
    except KeyboardInterrupt:
        sys.stderr.write(json.dumps({"error": "interrupted"}) + "\n")
        return EXIT_FAILED
    except Exception as exc:
        payload = {"error": f"{type(exc).__name__}: {exc}"}
        if args.pretty:
            import traceback

            sys.stderr.write(traceback.format_exc())
        else:
            sys.stderr.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return EXIT_FAILED
