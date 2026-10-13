"""Disk access: atomic writes and the two text formats the corpus is stored in.

Carved out of ``core.util`` because that module claimed to be part of the "shared floor"
with no state and no disk, and it was not true: the file-writing helpers, ``os`` and
``tempfile`` all lived there. ``util`` is now pure computation — normalisation, hashing,
tokenisation — and everything that touches a file is here. ``tests/test_purity.py`` holds
the line, because a claim in a docstring is not a boundary.

Every write goes through a temp file and an atomic replace, so a reader never sees a
half-written record and an interrupted run cannot leave a truncated one.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .util import json_dumps


def write_json_atomic(path: Path, obj: Any) -> None:
    """Write JSON via a temp file + replace so readers never see a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json_dumps(obj)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def append_jsonl(path: Path, obj: Any) -> None:
    """Append one event. Opens in text mode with explicit UTF-8 and '\\n'."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False, sort_keys=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for _lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # A torn final line (crash mid-append) must not make the ledger
                # unreadable; skip it and keep going.
                continue
    return out


__all__ = [
    "append_jsonl",
    "exclusive_lock",
    "read_json",
    "read_jsonl",
    "write_json_atomic",
    "write_text_atomic",
]


# --------------------------------------------------------------------------- #
# Cross-process mutation lock
# --------------------------------------------------------------------------- #

# Re-entrancy depth per resolved lock path. Mutation methods nest (an upsert takes the
# lock, then logs inside it), and two Library objects pointed at the same root in one
# process must not deadlock each other. Not thread-safe — the tool is single-threaded
# per process; add a threading lock here if that ever changes.
_LOCK_HELD: dict[str, int] = {}


@contextmanager
def exclusive_lock(path: Path):
    """Hold a cross-process exclusive lock on ``path`` (created as needed).

    Windows locks one byte through ``msvcrt.locking``; POSIX uses ``flock``.
    Acquisition blocks (msvcrt gives up after ~10 s and raises — hold times here are
    milliseconds, so both are comfortable). The file is never deleted: an empty lock
    file sitting next to the data it guards is the normal steady state.
    """
    try:
        key = str(path.resolve())
    except OSError:
        key = str(path)
    if _LOCK_HELD.get(key, 0) > 0:
        _LOCK_HELD[key] += 1
        try:
            yield
        finally:
            _LOCK_HELD[key] -= 1
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR)
    _LOCK_HELD[key] = 1
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        _LOCK_HELD[key] -= 1
        if _LOCK_HELD[key] <= 0:
            del _LOCK_HELD[key]
        os.close(fd)
