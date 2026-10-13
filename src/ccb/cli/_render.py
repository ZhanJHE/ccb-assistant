"""Human rendering of command payloads.

Machine callers get JSON; ``--pretty`` is a convenience for people, and it must never be
the thing that decides whether a command worked.
"""

from __future__ import annotations

import argparse
import json

from .. import ops


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def _record_keys_for(args: argparse.Namespace) -> tuple[str, ...]:
    """Which payload keys hold record lists, for the operation that just ran.

    Declared by the operation in ``ccb.ops``, never inferred from the payload: `works`
    is a count in ``library stats`` and a list in ``library list``, and the renderer used
    to guess between them and crash.
    """
    command = getattr(args, "command", "") or ""
    action = getattr(args, "action", "") or getattr(args, "topics_action", "") or ""
    op = ops.BY_PATH.get(f"{command} {action}" if action else command)
    return op.records_key if op else ()


def _render_pretty(payload: dict[str, Any], record_keys: tuple[str, ...] = ()) -> str:
    """Readable rendering for humans; never used by machine callers.

    Which payload keys hold record lists is *declared by the command that produced the
    payload*, not inferred here. The previous version guessed with
    ``local_hits or fetched or works`` and crashed on ``library stats``, where ``works``
    is a count — the same key means different things in different commands, so a renderer
    that sniffs shapes will eventually meet a payload that breaks it. The type is still
    checked before iterating, because a declared key can legitimately hold a scalar.
    """
    lines: list[str] = []
    for key in ("message", "note", "error"):
        if payload.get(key):
            lines.append(f"{key}: {payload[key]}")
    for chan, err in (payload.get("errors") or {}).items():
        lines.append(f"  ! {chan}: {err}")
    for warn in payload.get("warnings") or []:
        lines.append(f"  ~ {warn}")
    for key in record_keys:
        rows = payload.get(key)
        if not isinstance(rows, list) or not rows:
            continue
        lines.append("")
        if len(record_keys) > 1:
            lines.append(f"  {key}:")
        for r in rows:
            if not isinstance(r, dict):
                lines.append(f"  {r}")
                continue
            year = r.get("year") or "----"
            venue = r.get("venue") or ""
            flags = []
            if r.get("has_pdf"):
                flags.append("PDF")
            if r.get("has_fulltext"):
                flags.append("text")
            if r.get("local"):
                flags.append("local")
            flag_str = f" [{' '.join(flags)}]" if flags else ""
            lines.append(f"  {r.get('work_id', '?')}")
            lines.append(f"    {year}  {str(r.get('title', ''))[:110]}")
            if venue:
                lines.append(f"    {venue[:110]}")
            if flag_str:
                lines.append(f"    {flag_str.strip()}")
    if not lines:
        lines.append(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return "\n".join(lines)
