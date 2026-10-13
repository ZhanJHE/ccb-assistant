"""Blob storage: PDFs, extracted full text and passages.

Split out of store.py: content-addressed files under files/ and blobs/, derived
passages included - every write atomic, every read self-healing where a source hash
allows it. Methods run under the caller's lock; the *record* mutations (attach_*) stay
on the Library, which is also why a self-healing read re-enters the locked
``store_passages`` through the Library rather than writing directly.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..core.files import read_json, write_json_atomic, write_text_atomic
from ..core.util import fs_safe, sha256_bytes, sha256_text, utc_now

if TYPE_CHECKING:  # pragma: no cover
    from .store import Library


class FulltextStore:
    """Bytes and text under files/ and blobs/, content-addressed."""

    def __init__(self, lib: "Library"):
        self._lib = lib

    def store_file(self, data: bytes, *, ext: str = "pdf") -> tuple[str, str, int]:
        """Content-address bytes into `files/`. Identical bytes are stored once.

        Returns (sha256, library-relative path, size).
        """
        digest = sha256_bytes(data)
        rel = Path("files") / digest[:2] / f"{digest}.{ext}"
        abs_path = self._lib.root / rel
        if not abs_path.exists():
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = abs_path.with_suffix(abs_path.suffix + ".part")
            tmp.write_bytes(data)
            os.replace(tmp, abs_path)
        return digest, str(rel).replace("\\", "/"), len(data)

    def store_fulltext(self, work_id: str, text: str) -> tuple[str, int]:
        rel = Path("blobs") / fs_safe(work_id) / "fulltext.txt"
        abs_path = self._lib.root / rel
        write_text_atomic(abs_path, text)
        return str(rel).replace("\\", "/"), len(text)

    def passages_path(self, work_id: str) -> Path:
        """Absolute path of a work's passage index.

        Exposed because the on-disk name is escaped (a DOI contains "/") and callers
        that reconstruct it by hand get a path that does not exist. Deriving it in one
        place keeps tests, tools and the library agreeing on the layout.
        """
        return self._lib.root / Path("blobs") / fs_safe(work_id) / "passages.json"

    def store_passages(
        self, work_id: str, passages: list[Any], *, source_sha256: str = ""
    ) -> tuple[str, int]:
        """Persist the passage index for a work, next to its full text.

        Derived from the full text and rebuildable, but stored because rebuilding it on
        every question would mean re-tokenising every paper in the corpus - the same
        "do not redo the work" principle the rest of the tool follows.

        `source_sha256` records which full text this index was built from. Without it,
        re-extracting a PDF would leave a stale passage index in place and searches
        would keep hitting text that is no longer on disk - a derived artefact silently
        disagreeing with its source.
        """
        rel = Path("blobs") / fs_safe(work_id) / "passages.json"
        abs_path = self.passages_path(work_id)
        payload = {
            "work_id": work_id,
            "count": len(passages),
            "built_at": utc_now(),
            "source_sha256": source_sha256,
            "passages": [p.as_dict(with_text=True) for p in passages],
        }
        write_json_atomic(abs_path, payload)
        return str(rel).replace("\\", "/"), len(passages)

    def read_passages(self, work: Any) -> list[Any]:
        """Load a work's passages, rebuilding them whenever the source text changed.

        Self-healing rather than strict: a library created before this index existed, or
        one whose passage file was deleted or invalidated by a re-extraction, must still
        be answerable rather than requiring a migration step an agent would have to
        remember.
        """
        from .passages import chunk_text, load_passages

        text = self._lib.read_fulltext(work)
        if not text:
            return []
        digest = sha256_text(text)
        abs_path = self.passages_path(work.work_id)
        if abs_path.exists():
            data = read_json(abs_path, default={}) or {}
            cached = load_passages(data)
            recorded = str(data.get("source_sha256") or "")
            if cached and recorded and recorded == digest:
                return cached
            if cached and not recorded:
                # Built by an older version that did not record the source hash; adopt
                # it rather than forcing a rebuild of the whole corpus.
                return cached
        passages = chunk_text(text, work_id=work.work_id)
        if passages:
            self._lib.store_passages(work.work_id, passages, source_sha256=digest)
        return passages

    def read_fulltext(self, work: Any) -> str:
        for m in work.manifestations:
            if m.fulltext_path:
                p = self._lib.root / m.fulltext_path
                if p.exists():
                    return p.read_text(encoding="utf-8", errors="replace")
        return ""

    def file_abs(self, rel_path: str) -> Path:
        return self._lib.root / rel_path
