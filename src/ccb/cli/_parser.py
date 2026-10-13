"""The argument parser, generated from ``ccb.ops``.

One operation table (``ops.py``) drives all three faces; this module is the CLI half of
that derivation, so a new parameter cannot exist on one face and be missing on another.
"""

from __future__ import annotations

import argparse
from typing import Any

from .. import __version__, ops
from . import _handlers
from ._context import CommandError


# --------------------------------------------------------------------------- #
# Operations -> argparse
# --------------------------------------------------------------------------- #


def _add_params(sp: argparse.ArgumentParser, op: ops.Operation) -> None:
    """Declare one operation's parameters on its subparser.

    Derived from the same declarations the MCP schema and the contract use, so a new
    parameter cannot exist on one face and be missing on another. ``mcp_only`` params are
    skipped: the CLI reaches those through a global flag instead.
    """
    for param in op.params:
        if param.mcp_only:
            continue
        kwargs: dict[str, Any] = {}
        if param.help:
            kwargs["help"] = param.help
        if param.choices:
            kwargs["choices"] = list(param.choices)
        if param.kind == "flag":
            sp.add_argument(*param.cli.split("|"), action="store_true",
                            dest=param.argparse_dest, default=param.default, **kwargs)
        elif param.cli:
            sp.add_argument(*param.cli.split("|"), dest=param.argparse_dest,
                            type=int if param.kind == "int" else str,
                            default=param.default, **kwargs)
        elif param.required:
            sp.add_argument(param.name, **kwargs)
        else:
            sp.add_argument(param.name, nargs="?", default=param.default, **kwargs)


def _add_operations(sub: Any, common: argparse.ArgumentParser) -> None:
    """Build every subparser from ``ccb.ops``.

    Grouped operations (``library``, ``topics``) get a parent subcommand whose nested
    subparsers carry the actions, and each parent declares the ``dest`` its handler
    already reads, so ``args.action`` and ``args.topics_action`` keep working.
    """
    handlers = {
        name: obj for name, obj in vars(_handlers).items()
        if name.startswith("cmd_") and callable(obj)
    }
    nesting: dict[str, Any] = {}
    for op in ops.OPERATIONS:
        if op.group:
            target = nesting.get(op.group)
            if target is None:
                info = ops.GROUP_INFO[op.group]
                parent = sub.add_parser(op.group, parents=[common], help=info["help"],
                                        description=info.get("description"))
                target = parent.add_subparsers(dest=info["dest"], required=True)
                nesting[op.group] = target
        else:
            target = sub
        sp = target.add_parser(op.name, parents=[common], help=op.summary)
        _add_params(sp, op)
        sp.set_defaults(func=handlers[op.handler])



def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ccb",
        description=(
            "Aggregate every paper search/download channel behind one entry point, and "
            "keep a durable local library so nothing is fetched or parsed twice."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Run `ccb contract` for the operating rules and the exact step order.\n"
            "Exit codes: 0 ok, 2 usage, 3 not found, 4 partial (some channels failed), "
            "5 failed."
        ),
    )
    p.add_argument("--version", action="version", version=f"ccb {__version__}")
    p.add_argument("--library", help="library root (default: $CCB_HOME, else <checkout>/papers)")
    p.add_argument("--pretty", action="store_true", help="human-readable output instead of JSON")
    p.add_argument("--offline", action="store_true", help="never touch the network")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--channel", help="comma-separated channel allow-list")
    p.add_argument("--disable-channel", help="comma-separated channels to disable")

    # The same global flags are attached to every subparser so they may appear *after*
    # the subcommand as well. argparse only accepts them before it, which trips everyone
    # who appends `--pretty` to the command they just typed — including the probe script
    # written for this repository. Each copy defaults to SUPPRESS so an absent occurrence
    # leaves the value parsed at the top level untouched.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--library", default=argparse.SUPPRESS,
                        help="library root (default: $CCB_HOME, else <checkout>/papers)")
    common.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS,
                        help="human-readable output instead of JSON")
    common.add_argument("--offline", action="store_true", default=argparse.SUPPRESS,
                        help="never touch the network")
    common.add_argument("--verbose", action="store_true", default=argparse.SUPPRESS)
    common.add_argument("--channel", default=argparse.SUPPRESS,
                        help="comma-separated channel allow-list")
    common.add_argument("--disable-channel", default=argparse.SUPPRESS,
                        help="comma-separated channels to disable")

    sub = p.add_subparsers(dest="command", required=True)
    _add_operations(sub, common)

    return p
