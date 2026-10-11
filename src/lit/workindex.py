"""The derived query index — a cache, never a source of truth.

`works/*.json` is authoritative; `index.sqlite` exists only to make queries and
identity lookups fast. That asymmetry is deliberate and it shapes this whole module:
every derived artefact must be rebuildable from the JSON files, so a damaged or
missing index is an inconvenience rather than data loss.

Two responsibilities live here:

* **the index itself** — schema, per-work writes, lookups, deletions, rebuilds;
* **consistency checking** — detecting that the index has drifted from the work files
  and repairing it, so an agent that skips a maintenance step still gets correct
  answers.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .util import read_json, utc_now, write_json_atomic

if TYPE_CHECKING:  # avoid a hard import cycle; Library owns the records
    from .library import Library
    from .model import WorkRecord

WORK_FILE_GLOB = "**/*.json"


class WorkIndex:
    """SQLite-backed index over the work files, plus its own drift detection."""

    def __init__(self, library: "Library"):
        self.library = library
        self.root = library.root
        self.index_path = library.index_path
        self._conn: sqlite3.Connection | None = None
        # The consistency check runs at most once per process: it costs an O(n) stat
        # walk, which is fine before the first query of a command and wasteful after.
        self._checked = False

    # ------------------------------------------------------------------ #
    # Connection and schema
    # ------------------------------------------------------------------ #

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.index_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.commit()
            except Exception:
                pass
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def ensure_schema(self) -> None:
        """Create the tables if they are absent. A no-op when already correct."""
        conn = self.connect()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS works ("
            " work_id TEXT PRIMARY KEY, title TEXT, year INTEGER, venue TEXT,"
            " authors TEXT, abstract TEXT, has_pdf INTEGER, has_fulltext INTEGER,"
            " doi TEXT, arxiv_id TEXT, openreview_id TEXT, check_status TEXT,"
            " updated_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ids ("
            " scheme TEXT, value TEXT, work_id TEXT, PRIMARY KEY (scheme, value))"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS aliases (alias TEXT PRIMARY KEY, work_id TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS blocks (block TEXT, work_id TEXT,"
            " PRIMARY KEY (block, work_id))"
        )
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS works_fts USING fts5("
            " work_id UNINDEXED, title, abstract, authors, venue)"
        )
        conn.commit()

    def _ensure(self) -> None:
        """Check drift once per process, then guarantee the schema exists."""
        if not self._checked:
            self._checked = True
            try:
                self.self_check(repair=True)
            except Exception:
                # A failed self-check must not take down reads; fall through to the
                # plain CREATE-IF-NOT-EXISTS path so queries still work.
                pass
        self.ensure_schema()

    # ------------------------------------------------------------------ #
    # Consistency: detect drift, repair what is safe
    # ------------------------------------------------------------------ #

    def self_check(self, *, repair: bool = True) -> dict[str, Any]:
        """Verify the derived artefacts against the work files.

        Exists because an agent *will* eventually skip a step or edit a file by hand.
        Rather than relying on discipline, this detects drift and fixes it:

        * index missing, unreadable, or built from a different set of work files than
          what is on disk  ->  rebuild from the JSON source of truth;
        * a work file that fails to parse  ->  reported, never silently dropped;
        * a ledger shorter than the works it describes  ->  reported, never rewritten
          (the ledger is append-only).
        """
        library = self.library
        report: dict[str, Any] = {"checked_at": utc_now(), "repaired": [], "problems": []}
        if not library.exists:
            library.init()
            report["repaired"].append("initialized empty library")

        bad_files: list[str] = []
        n_works = 0
        for p in sorted(library.works_dir.glob(WORK_FILE_GLOB)):
            n_works += 1
            try:
                d = read_json(p)
                if not isinstance(d, dict) or not d.get("work_id"):
                    bad_files.append(str(p.relative_to(library.root)))
            except Exception as exc:
                bad_files.append(f"{p.relative_to(library.root)} ({type(exc).__name__})")
        report["works_on_disk"] = n_works
        if bad_files:
            report["problems"].append(
                {"kind": "unreadable_work_files", "count": len(bad_files), "files": bad_files[:20]}
            )

        fingerprint = self.works_fingerprint(n_works)
        meta = library.meta()
        indexed = int(meta.get("works", -1))
        index_ok = True
        reason = ""
        if not self.index_path.exists():
            index_ok, reason = False, "index file missing"
        elif indexed != n_works:
            index_ok, reason = False, f"index holds {indexed} works, disk has {n_works}"
        elif meta.get("works_fingerprint") and meta.get("works_fingerprint") != fingerprint:
            index_ok, reason = False, "index fingerprint does not match work files"
        elif bad_files:
            index_ok, reason = False, "work files could not all be read"

        report["index_ok"] = index_ok
        if not index_ok:
            report["index_reason"] = reason
            if repair:
                rebuilt = self.reindex()
                report["repaired"].append(f"rebuilt index ({reason})")
                report["works_indexed"] = rebuilt["works"]
                # Report the state *after* repair, or a caller checking index_ok would
                # wrongly conclude the library is broken.
                report["index_ok"] = True
                report["index_was_repaired"] = True
            else:
                report["problems"].append({"kind": "index_stale", "reason": reason})
        else:
            library._save_meta(works_fingerprint=fingerprint)

        creations = len(library.ledger(event="work_created"))
        if n_works and creations < n_works:
            report["problems"].append(
                {
                    "kind": "ledger_shorter_than_library",
                    "works": n_works,
                    "work_created_events": creations,
                    "note": "ledger is append-only; missing history is reported, not rewritten",
                }
            )
        return report

    def repair(self) -> dict[str, Any]:
        """Force a full rebuild and report every problem found beforehand."""
        self._checked = True
        report = self.self_check(repair=False)
        rebuilt = self.reindex()
        report["repaired"].append("full index rebuild")
        report["works_indexed"] = rebuilt["works"]
        report["index_ok"] = True
        self.library.log("repair", {"works": rebuilt["works"]})
        return report

    def works_fingerprint(self, n_works: int | None = None) -> str:
        """Cheap corpus fingerprint: count plus per-file size and mtime.

        Not a content hash — that would defeat the purpose of a startup check. Together
        with the recorded work count it catches the realistic drift cases: a file added,
        removed or rewritten outside the program.
        """
        h = hashlib.sha256()
        if n_works is None:
            n_works = len(self.library.all_work_ids())
        h.update(str(n_works).encode())
        for p in sorted(self.library.works_dir.glob(WORK_FILE_GLOB)):
            try:
                st = p.stat()
            except OSError:
                continue
            h.update(p.name.encode("utf-8", errors="replace"))
            h.update(str(st.st_size).encode())
            h.update(str(int(st.st_mtime)).encode())
        return h.hexdigest()[:32]

    # ------------------------------------------------------------------ #
    # Rebuild
    # ------------------------------------------------------------------ #

    def reindex(self) -> dict[str, Any]:
        """Rebuild the whole index from the JSON files."""
        # Marked checked first: reindex legitimately runs while the index is stale, and
        # re-entering the self-check from inside it would recurse.
        self._checked = True
        self.ensure_schema()
        conn = self.connect()
        for t in ("works", "ids", "aliases", "blocks"):
            conn.execute(f"DELETE FROM {t}")
        try:
            conn.execute("DELETE FROM works_fts")
        except sqlite3.OperationalError:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS works_fts USING fts5("
                " work_id UNINDEXED, title, abstract, authors, venue)"
            )
        conn.commit()
        n = 0
        for w in self.library.iter_works():
            self.index_work(w, commit=False)
            n += 1
        conn.commit()
        self.library._save_meta(
            works=self.library.count(),
            last_reindex=utc_now(),
            works_fingerprint=self.works_fingerprint(),
        )
        self.library.log("reindex", {"works": n})
        return {"works": n}

    def index_work(self, work: "WorkRecord", *, commit: bool = True) -> None:
        """Write one work's derived rows. Called from the single library write path."""
        self._ensure()
        conn = self.connect()
        conn.execute(
            "INSERT OR REPLACE INTO works (work_id,title,year,venue,authors,abstract,"
            " has_pdf,has_fulltext,doi,arxiv_id,openreview_id,check_status,updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                work.work_id,
                work.title(),
                work.year(),
                work.venue(),
                json.dumps(work.authors(), ensure_ascii=False),
                work.abstract()[:20000],
                1 if work.has_pdf() else 0,
                1 if work.has_fulltext() else 0,
                work.ids.get("doi", ""),
                work.ids.get("arxiv", ""),
                work.ids.get("openreview", ""),
                work.check_status,
                work.updated_at,
            ),
        )
        conn.execute("DELETE FROM ids WHERE work_id = ?", (work.work_id,))
        for scheme, value in work.ids.items():
            if value:
                conn.execute(
                    "INSERT OR REPLACE INTO ids (scheme,value,work_id) VALUES (?,?,?)",
                    (scheme, value, work.work_id),
                )
        conn.execute("DELETE FROM aliases WHERE work_id = ?", (work.work_id,))
        for a in work.aliases:
            conn.execute(
                "INSERT OR REPLACE INTO aliases (alias,work_id) VALUES (?,?)", (a, work.work_id)
            )
        conn.execute("DELETE FROM blocks WHERE work_id = ?", (work.work_id,))
        keys = work.dedup_keys()
        for block in self.block_keys(keys.year, keys.title_norm):
            conn.execute(
                "INSERT OR REPLACE INTO blocks (block,work_id) VALUES (?,?)", (block, work.work_id)
            )
        conn.execute("DELETE FROM works_fts WHERE work_id = ?", (work.work_id,))
        conn.execute(
            "INSERT INTO works_fts (work_id,title,abstract,authors,venue) VALUES (?,?,?,?,?)",
            (work.work_id, work.title(), work.abstract(), " ".join(work.authors()), work.venue()),
        )
        if commit:
            conn.commit()

    def deindex_work(self, work_id: str, *, keep_aliases: bool = False) -> None:
        """Remove a work's derived rows.

        Used when a work stops existing in its own right (merged into another). The
        `aliases` rows are deliberately preserved when merging — that is exactly what
        keeps the absorbed identifier resolvable. Leaving the `works`/`ids` rows behind
        instead makes the old id resolve to a record that is no longer on disk, so a
        caller holding a previously valid id silently gets nothing.
        """
        self._ensure()
        conn = self.connect()
        conn.execute("DELETE FROM works WHERE work_id = ?", (work_id,))
        conn.execute("DELETE FROM ids WHERE work_id = ?", (work_id,))
        conn.execute("DELETE FROM blocks WHERE work_id = ?", (work_id,))
        conn.execute("DELETE FROM works_fts WHERE work_id = ?", (work_id,))
        if not keep_aliases:
            conn.execute("DELETE FROM aliases WHERE work_id = ?", (work_id,))
        conn.commit()

    # ------------------------------------------------------------------ #
    # Lookups
    # ------------------------------------------------------------------ #

    def lookup_key(self, key: str) -> str:
        """Resolve a work id or an alias to the surviving work id."""
        self._ensure()
        row = self.connect().execute(
            "SELECT work_id FROM works WHERE work_id = ?", (key,)
        ).fetchone()
        if row:
            return row[0]
        row = self.connect().execute(
            "SELECT work_id FROM aliases WHERE alias = ?", (key,)
        ).fetchone()
        return row[0] if row else ""

    def lookup_id(self, scheme: str, value: str) -> str:
        self._ensure()
        row = self.connect().execute(
            "SELECT work_id FROM ids WHERE scheme = ? AND value = ?", (scheme, value)
        ).fetchone()
        return row[0] if row else ""

    def lookup_alias(self, alias: str) -> str:
        self._ensure()
        row = self.connect().execute(
            "SELECT work_id FROM aliases WHERE alias = ?", (alias,)
        ).fetchone()
        return row[0] if row else ""

    def block_members(self, block: str) -> list[str]:
        self._ensure()
        rows = self.connect().execute(
            "SELECT work_id FROM blocks WHERE block = ?", (block,)
        ).fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------ #
    # Query
    # ------------------------------------------------------------------ #

    def query(
        self,
        query: str = "",
        *,
        year_from: int | None = None,
        year_to: int | None = None,
        venue: str = "",
        author: str = "",
        has_pdf: bool | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        self._ensure()
        conn = self.connect()
        sql = [
            "SELECT w.work_id, w.title, w.year, w.venue, w.authors, w.has_pdf,",
            "       w.has_fulltext, w.openreview_id, w.arxiv_id, w.doi",
            "FROM works w",
        ]
        where: list[str] = []
        params: list[Any] = []
        if query:
            sql.append("JOIN works_fts f ON f.work_id = w.work_id")
            where.append("works_fts MATCH ?")
            params.append(_fts_query(query))
        if year_from is not None:
            where.append("w.year >= ?")
            params.append(year_from)
        if year_to is not None:
            where.append("w.year <= ?")
            params.append(year_to)
        if venue:
            where.append("w.venue LIKE ?")
            params.append(f"%{venue}%")
        if author:
            where.append("w.authors LIKE ?")
            params.append(f"%{author}%")
        if has_pdf is not None:
            where.append("w.has_pdf = ?")
            params.append(1 if has_pdf else 0)
        if where:
            sql.append("WHERE " + " AND ".join(where))
        sql.append("ORDER BY w.year DESC, w.title ASC LIMIT ?")
        params.append(limit)
        rows = conn.execute(" ".join(sql), params).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "work_id": r[0],
                    "title": r[1],
                    "year": r[2],
                    "venue": r[3],
                    "authors": json.loads(r[4] or "[]"),
                    "has_pdf": bool(r[5]),
                    "has_fulltext": bool(r[6]),
                    "openreview_id": r[7] or "",
                    "arxiv_id": r[8] or "",
                    "doi": r[9] or "",
                    "local": True,
                }
            )
        return out

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def block_keys(year: int | None, title_norm: str) -> list[str]:
        """Blocking keys for dedup.

        Buckets by year (with a ±1 tolerance) crossed with two title-token prefixes, so
        a comparison never has to touch the whole library. Two prefixes rather than one
        because a subtitle can shift the leading tokens.
        """
        toks = title_norm.split()
        prefixes = []
        if toks:
            prefixes.append(" ".join(toks[:2]))
        if len(toks) > 3:
            prefixes.append(" ".join(toks[2:4]))
        years = [year - 1, year, year + 1] if year is not None else [None]
        return [f"{y or 'x'}|{p}" for y in years for p in prefixes if p]


def _fts_query(query: str) -> str:
    """Turn a user query into a safe FTS5 MATCH expression (prefix-OR terms).

    Every term is quoted, so user punctuation cannot inject FTS5 operators.
    """
    tokens = [
        t
        for t in "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in query).split()
        if t
    ]
    if not tokens:
        return '""'
    return " OR ".join(f'"{t}"*' for t in tokens[:12])


def write_meta(meta_path: Path, meta: dict[str, Any]) -> None:
    write_json_atomic(meta_path, meta)
