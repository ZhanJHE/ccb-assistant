"""Codemod: move the derived-index methods out of Library into WorkIndex.

Library had grown to 52 methods and ~1250 lines with two clearly separable jobs (the
corpus and its query index). This script performs the mechanical part of the split and
is kept as a record of exactly what moved. Run from the repo root:

    python tools/_codemod_split_index.py
"""

from __future__ import annotations

import ast
import pathlib
import sys

TARGET = pathlib.Path("src/lit/library.py")

# Methods relocated verbatim into workindex.WorkIndex.
MOVED = {
    "self_check": "self_check",
    "repair": "repair",
    "_works_fingerprint": "works_fingerprint",
    "_connect": "connect",
    "_ensure_index": "_ensure",
    "reindex": "reindex",
    "_index_work": "index_work",
    "_block_keys": "block_keys",
    "_deindex_work": "deindex_work",
    "_lookup_index_key": "lookup_key",
    "_lookup_index_id": "lookup_id",
    "_lookup_index_alias": "lookup_alias",
    "_index_block": "block_members",
}

# Call-site rewrites inside Library and in other modules.
CALL_REWRITES = {
    "self._ensure_index()": "self._index._ensure()",
    "self._save_meta(": "self._save_meta(",
    "self._index_work(": "self._index.index_work(",
    "self._deindex_work(": "self._index.deindex_work(",
    "self._lookup_index_key(": "self._index.lookup_key(",
    "self._lookup_index_id(": "self._index.lookup_id(",
    "self._lookup_index_alias(": "self._index.lookup_alias(",
    "self._index_block(": "self._index.block_members(",
    "self._works_fingerprint(": "self._index.works_fingerprint(",
}


def strip_method(source: str, name: str) -> str:
    """Remove one method (with its preceding decorators/comments) from the source."""
    tree = ast.parse(source)
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Library"
    )
    node = next(
        n
        for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    lines = source.splitlines(keepends=True)
    start = node.lineno - 1
    # Absorb a directly preceding decorator, plus the blank line above it.
    while start > 0 and lines[start - 1].lstrip().startswith("@"):
        start -= 1
    end = node.end_lineno  # 1-based inclusive -> exclusive slice end
    while end < len(lines) and not lines[end].strip():
        end += 1
    return "".join(lines[:start] + lines[end:])


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")

    # 1. Construction: create the index collaborator.
    source = source.replace(
        "        self._work_cache: dict[str, WorkRecord] = {}\n"
        "        self._conn: sqlite3.Connection | None = None\n"
        "        self._index_checked = False\n",
        "        self._work_cache: dict[str, WorkRecord] = {}\n"
        "        # The derived query index lives in its own collaborator: it is a cache\n"
        "        # over the work files, not part of the corpus's identity.\n"
        "        self._index = WorkIndex(self)\n",
        1,
    )

    # 2. Rewrite call sites.
    for old, new in CALL_REWRITES.items():
        if old != new:
            source = source.replace(old, new)

    # 3. Drop the relocated methods.
    for name in MOVED:
        source = strip_method(source, name)

    # 4. Library.close()/__exit__ delegate.
    source = source.replace(
        '    def close(self) -> None:\n'
        '        """Release the SQLite handle (important on Windows, where it locks the file)."""\n'
        '        if self._conn is not None:\n'
        '            try:\n'
        '                self._conn.commit()\n'
        '            except Exception:\n'
        '                pass\n'
        '            try:\n'
        '                self._conn.close()\n'
        '            except Exception:\n'
        '                pass\n'
        '            self._conn = None\n',
        '    def close(self) -> None:\n'
        '        """Release the SQLite handle (important on Windows, where it locks the file)."""\n'
        '        self._index.close()\n',
        1,
    )

    # 5. Import the collaborator.
    source = source.replace(
        "from .util import (",
        "from .workindex import WORK_FILE_GLOB, WorkIndex\nfrom .util import (",
        1,
    )

    # 6. Drop the now-duplicated module-level glob constant (it lives in workindex).
    source = source.replace(
        '\n# Every place that enumerates work files uses this one pattern. `work_path_shard`\n'
        '# shards two levels deep, so a single-level glob would silently report an empty\n'
        '# library while individual lookups still succeeded.\n'
        'WORK_FILE_GLOB = "**/*.json"\n',
        "",
        1,
    )

    # 7. Add the index accessors used by the delegating methods.
    anchor = "    def count(self) -> int:\n        return len(self.all_work_ids())\n"
    if anchor in source:
        source = source.replace(
            anchor,
            anchor
            + "\n    # --- consistency (delegated to the derived index) --- #\n\n"
            "    def self_check(self, *, repair: bool = True) -> dict[str, Any]:\n"
            '        """Verify derived artefacts against the work files; repair drift."""\n'
            "        return self._index.self_check(repair=repair)\n\n"
            "    def repair(self) -> dict[str, Any]:\n"
            '        """Force a full rebuild of every derived artefact."""\n'
            "        return self._index.repair()\n\n"
            "    def reindex(self) -> dict[str, Any]:\n"
            '        """Rebuild the query index from the JSON work files."""\n'
            "        return self._index.reindex()\n",
            1,
        )

    TARGET.write_text(source, encoding="utf-8", newline="\n")
    print(f"rewrote {TARGET}; removed {len(MOVED)} methods")
    return 0


if __name__ == "__main__":
    sys.exit(main())
