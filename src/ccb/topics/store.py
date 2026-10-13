"""Where topic artefacts live on disk.

Everything the topics module produces is plain text under the library, next to the
corpus it was derived from::

    <library>/topics/
        index.json             mined-topic history and the de-duplication keys
        surveys/<id>.json      a domain survey
        records/<id>.json      a committed topic (skeleton, evidence, rating)
        drafts/<id>.md         the Markdown draft exported for a human to read

Plain JSON and Markdown, not a database, for the same reason the rest of the library
is: diffable, greppable, and rebuildable. Writes go through this one module and are
recorded in the library ledger, so a topic can always be traced to the run that made
it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from ..core.files import read_json, write_json_atomic, write_text_atomic
from ..core.util import utc_now

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..library.store import Library

TOPICS_DIRNAME = "topics"
INDEX_NAME = "index.json"

# Artefact kinds, each a directory under topics/.
KINDS = ("surveys", "candidates", "records", "drafts")

_SAFE_KEY = re.compile(r"^[A-Za-z0-9._-]+$")


def topics_root(library: "Library") -> Path:
    return library.root / TOPICS_DIRNAME


def _safe(key: str) -> str:
    """Refuse a key that could escape the directory it is supposed to name."""
    if not key or not _SAFE_KEY.match(key) or ".." in key:
        raise ValueError(f"unsafe artefact key: {key!r}")
    return key


def artefact_path(library: "Library", kind: str, key: str, *, suffix: str = ".json") -> Path:
    if kind not in KINDS:
        raise ValueError(f"unknown artefact kind: {kind!r}")
    return topics_root(library) / kind / f"{_safe(key)}{suffix}"


def save_json(library: "Library", kind: str, key: str, payload: dict[str, Any]) -> Path:
    path = artefact_path(library, kind, key)
    with library.locked():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, payload)
        library.log(f"topics_{kind[:-1]}_saved", {"key": key, "path": str(path)})
    return path


def load_json(library: "Library", kind: str, key: str) -> dict[str, Any] | None:
    path = artefact_path(library, kind, key)
    if not path.exists():
        return None
    data = read_json(path, default=None)
    return data if isinstance(data, dict) else None


def list_json(library: "Library", kind: str) -> list[dict[str, Any]]:
    """Every artefact of a kind, newest first by the recorded timestamp."""
    directory = topics_root(library) / kind
    if not directory.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        data = read_json(path, default=None)
        if isinstance(data, dict):
            out.append(data)
    out.sort(key=lambda d: str(d.get("created_at") or ""), reverse=True)
    return out


def save_text(library: "Library", kind: str, key: str, text: str) -> Path:
    path = artefact_path(library, kind, key, suffix=".md")
    with library.locked():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(path, text)
        library.log(f"topics_{kind[:-1]}_written", {"key": key, "path": str(path)})
    return path


def read_text(library: "Library", kind: str, key: str) -> str:
    path = artefact_path(library, kind, key, suffix=".md")
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Mined-topic history: the mechanism behind "one at a time"
# --------------------------------------------------------------------------- #


def load_index(library: "Library") -> dict[str, Any]:
    path = topics_root(library) / INDEX_NAME
    data = read_json(path, default=None)
    if not isinstance(data, dict):
        return {"schema": 1, "created_at": utc_now(), "topics": [], "keys": []}
    data.setdefault("topics", [])
    data.setdefault("keys", [])
    return data


def _save_index(library: "Library", index: dict[str, Any]) -> Path:
    path = topics_root(library) / INDEX_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    index["updated_at"] = utc_now()
    write_json_atomic(path, index)
    return path


def mined_keys(library: "Library") -> set[str]:
    """The (gap x operator) keys already committed, so they are not proposed twice."""
    return {str(k) for k in load_index(library).get("keys", [])}


def remember_topic(library: "Library", record: dict[str, Any]) -> dict[str, Any]:
    """Record a committed topic in the index, with the keys it consumes."""
    index = load_index(library)
    topic_id = str(record.get("topic_id") or "")
    if not topic_id:
        raise ValueError("topic record has no topic_id")
    entry = {
        "topic_id": topic_id,
        "title": record.get("title", ""),
        "query": record.get("query", ""),
        "created_at": str(record.get("created_at") or utc_now()),
        "keys": list(record.get("dedup_keys", [])),
        "estimated_ccf": (record.get("rating") or {}).get("estimated_ccf", ""),
    }
    index["topics"] = [t for t in index["topics"] if t.get("topic_id") != topic_id]
    index["topics"].append(entry)
    known = {str(k) for k in index["keys"]}
    for key in entry["keys"]:
        if key not in known:
            index["keys"].append(key)
            known.add(key)
    _save_index(library, index)
    library.log("topics_topic_committed", {"topic_id": topic_id, "keys": entry["keys"]})
    return index


def list_topics(library: "Library", *, limit: int = 0) -> list[dict[str, Any]]:
    index = load_index(library)
    topics: Iterable[dict[str, Any]] = index.get("topics", [])
    ordered = sorted(topics, key=lambda t: str(t.get("created_at") or ""), reverse=True)
    return list(ordered[:limit] if limit else ordered)
