"""The append-only audit trail: live file, archive, and its maintenance.

Split out of store.py so the store is a coordinator rather than a container of every
concern; the ledger is self-contained state with exactly one write primitive (append)
plus one maintenance operation (compaction). Methods run under the caller's lock (the
Library delegates hold it).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ..core.files import append_jsonl, read_jsonl, write_text_atomic
from ..core.util import utc_now

if TYPE_CHECKING:  # pragma: no cover
    from .store import Library

LEDGER_ARCHIVE_NAME = "library.jsonl.archive"


class Ledger:
    """Append-only events across a live file and an append-only archive."""

    def __init__(self, lib: "Library"):
        self._lib = lib

    def log(self, event: str, payload: dict[str, Any] | None = None) -> None:
        append_jsonl(
            self._lib.ledger_path,
            {"at": utc_now(), "event": event, **(payload or {})},
        )

    def ledger(self, limit: int = 0, event: str = "") -> list[dict[str, Any]]:
        rows = read_jsonl(self._lib.ledger_path)
        if event:
            rows = [r for r in rows if r.get("event") == event]
        return rows[-limit:] if limit else rows

    def count_events(self, event: str) -> int:
        """Count an event across the live ledger **and** any archive.

        `check`'s integrity invariant - one `work_created` event per work - must
        survive a compaction: archived events still happened, so they are still counted.
        """
        n = sum(1 for r in read_jsonl(self._lib.ledger_path) if r.get("event") == event)
        n += self._archived_event_count(lambda r: r.get("event") == event)
        return n

    def _archived_event_count(self, predicate=None) -> int:
        """Rows in the ledger archive, optionally filtered. 0 when never compacted."""
        archive = self._lib.root / LEDGER_ARCHIVE_NAME
        if not archive.exists():
            return 0
        rows = read_jsonl(archive)
        if predicate is not None:
            return sum(1 for r in rows if predicate(r))
        return len(rows)

    def compact_ledger(self, keep: int = 2000) -> dict[str, Any]:
        """Move all but the newest `keep` events into an append-only archive.

        The live file stays the audit trail for everything recent; the archive is
        appended to and never rewritten, so nothing is lost - and `count_events` reads
        both, which is what keeps the self-check invariant true across a compaction.
        """
        rows = read_jsonl(self._lib.ledger_path)
        if len(rows) <= keep:
            return {
                "compacted": False,
                "events": len(rows),
                "reason": f"at or below the {keep}-event threshold",
            }
        head, tail = rows[:-keep], rows[-keep:]
        archive = self._lib.root / LEDGER_ARCHIVE_NAME
        with archive.open("a", encoding="utf-8", newline="\n") as fh:
            for row in head:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        write_text_atomic(
            self._lib.ledger_path,
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in tail),
        )
        self.log("ledger_compacted", {"archived": len(head), "kept": len(tail)})
        return {
            "compacted": True,
            "archived": len(head),
            "kept": len(tail) + 1,  # the ledger_compacted event just appended
            "archive": str(archive),
        }
