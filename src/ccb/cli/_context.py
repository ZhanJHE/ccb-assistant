"""Library handle, exit codes, and the errors a handler raises."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from ..core.paths import checkout_root
from ..library import Library, default_library_root
from ..search import Registry, Resolver
from ._render import _record_keys_for, _render_pretty


EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_PARTIAL = 4
EXIT_FAILED = 5


class CommandError(Exception):
    """A failure with an exit code attached."""

    def __init__(self, message: str, code: int = EXIT_FAILED, **extra: Any):
        super().__init__(message)
        self.message = message
        self.code = code
        self.extra = extra


# --------------------------------------------------------------------------- #
# Context
# --------------------------------------------------------------------------- #


class Context:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        root = Path(args.library).expanduser() if args.library else default_library_root()
        self.library = Library(root)
        self.library.ensure()
        self.registry = Registry(
            evidence=self.library.evidence,
            verbose=bool(getattr(args, "verbose", False)),
            config_paths=_config_paths(self.library),
            enabled=_split(args.channel) if getattr(args, "channel", "") else None,
            disabled=_split(getattr(args, "disable_channel", "")),
        )
        self.resolver = Resolver(
            self.library,
            self.registry,
            offline=bool(getattr(args, "offline", False)),
            verbose=bool(getattr(args, "verbose", False)),
        )

    def emit(self, payload: dict[str, Any], code: int = EXIT_OK) -> int:
        if getattr(self.args, "pretty", False):
            sys.stdout.write(
                _render_pretty(payload, _record_keys_for(self.args)) + "\n"
            )
        else:
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return code


def _config_paths(library: Library) -> list[Path]:
    paths: list[Path] = []
    env = os.environ.get("CCB_CHANNELS", "").strip()
    if env:
        paths.extend(Path(p) for p in env.split(os.pathsep) if p)
    paths.append(library.root / "channels.yaml")
    # The checkout is a first-class location now that the library lives inside it:
    # a channel declaration committed next to the code travels with the clone. The
    # cwd entry stays for callers that carry a config with them.
    checkout = checkout_root()
    cwd = Path.cwd()
    if checkout is not None and checkout != cwd:
        paths.append(checkout / "ccb-channels.yaml")
    paths.append(cwd / "ccb-channels.yaml")
    return paths


def _split(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _not_found(ctx: Context, identifier: str) -> CommandError:
    """A not-found error that says what to do next.

    An empty library and a missing paper are different facts; a caller that cannot
    tell them apart retries the wrong thing. A fresh clone starts empty by design —
    the corpus is local data, never shipped in the repository — so the empty case is
    the *first* thing a new user hits, not an edge case.
    """
    if ctx.library.count() == 0:
        return CommandError(
            f"{identifier!r} is not in the library, and the library is empty. Acquire "
            f'something first: `ccb find "<topic>"` then `ccb get <id> --with-pdf`',
            EXIT_NOT_FOUND,
        )
    return CommandError(
        f"{identifier!r} not found in the local library; run `ccb find`/`ccb get` for it",
        EXIT_NOT_FOUND,
    )
