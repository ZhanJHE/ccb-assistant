"""The persistent paper library.

This is the piece the landscape survey found missing: a durable, deduplicated local
corpus with stable identities and auditable provenance, rather than a pile of PDFs
that every session re-downloads and re-parses.

Design commitments:

* **Plain text is the source of truth.** Each work is one JSON file under
  ``works/``; ``library.jsonl`` records every mutation; ``index.sqlite`` is a
  *derived* artefact that can be deleted and rebuilt at any time. The library can
  therefore never reach a state where it is corrupt and unrecoverable — the worst
  case is a slow rebuild.
* **Local-first.** ``resolve()`` answers from disk with zero network calls. Callers
  only go to the network when it misses.
* **Conservative dedup.** Automatic merging requires strong evidence; anything
  ambiguous becomes an auditable ``merge_candidate`` instead of a silent merge,
  because a wrong merge poisons every citation downstream.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .evidence import EvidenceStore
from ..core.ids import compute_work_id, work_id_from_keys, work_path_shard
from ..core.paths import checkout_root
from ..core.model import (
    ChannelRecord,
    Manifestation,
    WorkRecord,
    add_claim,
    field_conflict,
    key_priority,
    merge_identifiers,
)
from .index import WORK_FILE_GLOB, WorkIndex
from ..core.files import append_jsonl, read_json, read_jsonl, write_json_atomic, write_text_atomic
from ..core.util import (
    jaccard,
    json_dumps,
    normalize_arxiv_id,
    normalize_doi,
    sha256_bytes,
    sha256_text,
    title_tokens,
    utc_now,
)

LIBRARY_SCHEMA = 1

# --- dedup thresholds ------------------------------------------------------- #
# Auto-merge demands near-identity. `MERGE_CANDIDATE` catches the plausible-but-
# uncertain band and hands it to a human/agent decision.
AUTO_MERGE_JACCARD = 0.92
MERGE_CANDIDATE_JACCARD = 0.60

DEFAULT_LIBRARY_DIRNAME = "papers"

@dataclass
class UpsertResult:
    """What happened when a record was offered to the library."""

    work_id: str
    action: str  # created | enriched | duplicate
    added_fields: list[str]
    merge_candidates: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "work_id": self.work_id,
            "action": self.action,
            "added_fields": self.added_fields,
            "merge_candidates": self.merge_candidates,
        }


@dataclass
class DedupCandidate:
    other_id: str
    score: float
    title_sim: float
    author_match: bool
    year_delta: int | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "other_id": self.other_id,
            "score": round(self.score, 4),
            "title_sim": round(self.title_sim, 4),
            "author_match": self.author_match,
            "year_delta": self.year_delta,
            "reason": self.reason,
        }


def default_library_root(cwd: Path | None = None) -> Path:
    """Resolve the library root.

    ``$CCB_HOME`` wins outright, then ``$CCB_REPO``, then the checkout the running
    code lives in, and only then a directory relative to ``cwd`` (which the last two
    cases need, and which only ``cwd`` itself supplies).

    The order is the point. A harness invokes the tool from the user's project, so a
    cwd-relative default scattered libraries across unrelated folders and left the
    clone — the one directory the user actually looks at — empty. Anchoring to the
    checkout makes "clone it and use it" true: the corpus lands inside the clone.

    An installed package has no checkout to anchor to; there the cwd fallback is the
    honest answer rather than a silent write into ``site-packages``.
    """
    env = os.environ.get("CCB_HOME")
    if env:
        return Path(env).expanduser()
    repo = os.environ.get("CCB_REPO", "").strip()
    if repo:
        return Path(repo).expanduser() / DEFAULT_LIBRARY_DIRNAME
    checkout = checkout_root()
    if checkout is not None:
        return checkout / DEFAULT_LIBRARY_DIRNAME
    base = Path(cwd) if cwd else Path.cwd()
    return base / DEFAULT_LIBRARY_DIRNAME


class Library:
    """The local corpus. No method here performs network I/O."""

    def __init__(self, root: Path | str, *, trust: Iterable[str] | None = None):
        self.root = Path(root)
        self.works_dir = self.root / "works"
        self.files_dir = self.root / "files"
        self.blobs_dir = self.root / "blobs"
        self.ledger_path = self.root / "library.jsonl"
        self.meta_path = self.root / "library.json"
        self.index_path = self.root / "index.sqlite"
        self.evidence = EvidenceStore(self.root / "evidence")
        self._trust = tuple(trust) if trust else None
        self._work_cache: dict[str, WorkRecord] = {}
        # The derived query index lives in its own collaborator: it is a cache
        # over the work files, not part of the corpus's identity.
        self._index = WorkIndex(self)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    @property
    def exists(self) -> bool:
        return self.meta_path.exists()

    def init(self, *, force: bool = False) -> dict[str, Any]:
        """Create the library skeleton. Idempotent unless ``force``."""
        if self.exists and not force:
            return self.meta()
        for d in (self.works_dir, self.files_dir, self.blobs_dir, self.root / "evidence"):
            d.mkdir(parents=True, exist_ok=True)
        meta = {
            "schema": LIBRARY_SCHEMA,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "key_chain_version": 1,
            "works": 0,
        }
        write_json_atomic(self.meta_path, meta)
        self.log("library_init", {"root": str(self.root)})
        return meta

    def ensure(self) -> None:
        if not self.exists:
            self.init()

    def meta(self) -> dict[str, Any]:
        return read_json(self.meta_path, default={}) or {}

    def _save_meta(self, **changes: Any) -> None:
        meta = self.meta()
        meta.update(changes)
        meta["updated_at"] = utc_now()
        write_json_atomic(self.meta_path, meta)

    # ------------------------------------------------------------------ #
    # Ledger — append-only audit trail
    # ------------------------------------------------------------------ #

    def log(self, event: str, payload: dict[str, Any] | None = None) -> None:
        append_jsonl(
            self.ledger_path,
            {"at": utc_now(), "event": event, **(payload or {})},
        )

    def ledger(self, limit: int = 0, event: str = "") -> list[dict[str, Any]]:
        rows = read_jsonl(self.ledger_path)
        if event:
            rows = [r for r in rows if r.get("event") == event]
        return rows[-limit:] if limit else rows

    # ------------------------------------------------------------------ #
    # Work storage
    # ------------------------------------------------------------------ #

    def work_path(self, work_id: str) -> Path:
        return self.works_dir / work_path_shard(work_id) / f"{_fs_safe(work_id)}.json"

    def load(self, work_id: str, *, use_cache: bool = True) -> WorkRecord | None:
        if use_cache and work_id in self._work_cache:
            return self._work_cache[work_id]
        d = read_json(self.work_path(work_id))
        if d is None:
            return None
        w = WorkRecord.from_dict(d)
        if use_cache:
            self._work_cache[work_id] = w
        return w

    def save(self, work: WorkRecord, *, log_event: str = "work_saved") -> None:
        """The single write path for the whole library.

        Every mutation goes through here so the three representations can never
        diverge: the work JSON (truth), the SQLite index (derived), and the ledger
        (audit). An agent cannot "forget" one of them because it never touches them
        individually — and re-running any command is idempotent.
        """
        work.updated_at = utc_now()
        write_json_atomic(self.work_path(work.work_id), work.as_dict())
        self._work_cache[work.work_id] = work
        self._index.index_work(work)
        self._save_meta(works=self.count(), works_fingerprint=self._index.works_fingerprint())
        self.log(log_event, {"work_id": work.work_id, "title": work.title()[:160]})

    def all_work_ids(self) -> list[str]:
        """Every work id in the library, read from the records themselves.

        Deliberately *not* derived from filenames. The filename is a lossy, escaped
        projection of the id (`|`, `/` and `:` are all percent-encoded), so decoding it
        piecemeal silently produced a different string than the one stored — which made
        alias comparison fail and work ids look inconsistent between call sites. The
        authoritative value is the `work_id` field inside each JSON file.
        """
        if not self.works_dir.exists():
            return []
        ids: list[str] = []
        for p in self.works_dir.glob(WORK_FILE_GLOB):
            try:
                d = read_json(p)
            except Exception:
                continue
            if isinstance(d, dict) and d.get("work_id"):
                ids.append(str(d["work_id"]))
                continue
            # Fallback for a file that cannot be parsed: unquote the whole stem so no
            # escape sequence is left half-decoded.
            from urllib.parse import unquote

            ids.append(unquote(p.stem))
        return sorted(set(ids))

    def iter_works(self) -> Iterable[WorkRecord]:
        """Yield every readable work.

        A file that fails to parse is skipped rather than raising: one damaged record
        must not make the whole library unreadable. `self_check` is what reports such
        files, so the problem is surfaced without taking the corpus down.
        """
        for wid in self.all_work_ids():
            try:
                w = self.load(wid, use_cache=False)
            except Exception:
                continue
            if w is not None:
                yield w

    def close(self) -> None:
        """Release the SQLite handle (important on Windows, where it locks the file)."""
        self._index.close()

    def __enter__(self) -> "Library":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def count(self) -> int:
        return len(self.all_work_ids())

    # --- consistency (delegated to the derived index) --- #

    def self_check(self, *, repair: bool = True) -> dict[str, Any]:
        """Verify derived artefacts against the work files; repair drift."""
        return self._index.self_check(repair=repair)

    def repair(self) -> dict[str, Any]:
        """Force a full rebuild of every derived artefact."""
        return self._index.repair()

    def reindex(self) -> dict[str, Any]:
        """Rebuild the query index from the JSON work files."""
        return self._index.reindex()

    # ------------------------------------------------------------------ #
    # Local-first resolution  ← the core of "don't redo the whole pipeline"
    # ------------------------------------------------------------------ #

    def resolve(self, identifier: str) -> WorkRecord | None:
        """Find a work by any identifier, alias, or id-fragment — zero network calls."""
        if not identifier:
            return None
        needle = identifier.strip()

        # 1. Exact work_id
        w = self.load(needle)
        if w is not None:
            return w

        # 2. Typed key ("doi:10.1234/x") or bare value.
        #
        # `parse_identifier` is always consulted, never only when the string looks
        # scheme-less: a URL contains a colon ("http://...") and so does an explicit
        # prefix ("arXiv:Xv5"), and guarding on ":" made both of those skip parsing
        # entirely and fail to resolve.
        from ..core.ids import parse_identifier

        parsed = parse_identifier(needle)
        candidates = [needle]
        if parsed is not None:
            candidates.append(parsed.key)
            # A bare identifier has no scheme to split on, so the typed-key form must be
            # built explicitly — otherwise a stored work_id of "doi:10.1/x" is
            # unreachable by the plain "10.1/x" a user or report would quote.
            if ":" not in needle:
                candidates.append(f"{parsed.scheme}:{parsed.value}")
        normalizers = {"doi": normalize_doi, "arxiv": normalize_arxiv_id}
        for cand in candidates:
            hit = self._index.lookup_key(cand)
            if hit:
                return self.load(hit)
            scheme, _, value = cand.partition(":")
            if scheme in ("doi", "arxiv", "openreview", "acl", "pmlr", "dblp", "pmid", "openalex"):
                # Normalize before the index lookup: the index stores canonical values
                # (a versionless arXiv id, a lowercased bare DOI), so "arXiv:Xv5" and a
                # full arXiv URL must reduce exactly the way the stored record did.
                norm_fn = normalizers.get(scheme)
                if norm_fn:
                    value = norm_fn(value)
                hit = self._index.lookup_id(scheme, value)
                if hit:
                    return self.load(hit)

        # 3. Alias
        hit = self._index.lookup_alias(needle)
        if hit:
            return self.load(hit)

        # 4. Slug/title fragment from the filename, as a last courtesy
        for p in self.works_dir.glob(WORK_FILE_GLOB):
            if needle.casefold() in p.stem.casefold():
                w = self.load(p.stem.replace("%3A", ":"), use_cache=False)
                if w is not None:
                    return w
        return None

    # ------------------------------------------------------------------ #
    # Ingestion
    # ------------------------------------------------------------------ #

    def upsert_record(
        self,
        rec: ChannelRecord,
        *,
        auto_merge: bool = True,
        record_event: bool = True,
    ) -> UpsertResult:
        """Fold one channel record into the library, deduplicating as it goes."""
        work = rec.to_work()
        return self.upsert_work(work, auto_merge=auto_merge, record_event=record_event)

    def upsert_work(
        self,
        incoming: WorkRecord,
        *,
        auto_merge: bool = True,
        record_event: bool = True,
    ) -> UpsertResult:
        target = self._find_existing(incoming)
        if target is not None:
            added = self._absorb(target, incoming)
            self.save(target, log_event="work_enriched" if added else "work_touched")
            if record_event and added:
                self.log(
                    "fields_added",
                    {"work_id": target.work_id, "fields": added, "src": _sources_of(incoming)},
                )
            return UpsertResult(target.work_id, "enriched" if added else "duplicate", added, [])

        candidates = self.dedup_candidates(incoming)
        if auto_merge and candidates:
            top = candidates[0]
            if top.score >= AUTO_MERGE_JACCARD:
                existing = self.load(top.other_id)
                if existing is not None:
                    added = self._absorb(existing, incoming)
                    self.save(existing, log_event="work_merged_auto")
                    self.log(
                        "auto_merge",
                        {
                            "into": existing.work_id,
                            "from": incoming.work_id,
                            "score": round(top.score, 4),
                            "reason": top.reason,
                        },
                    )
                    return UpsertResult(existing.work_id, "enriched", added, [])

        self.save(incoming, log_event="work_created")
        flagged = [c.as_dict() for c in candidates if c.score >= MERGE_CANDIDATE_JACCARD]
        if record_event:
            self.log(
                "work_created",
                {"work_id": incoming.work_id, "title": incoming.title()[:160],
                 "merge_candidates": flagged},
            )
        return UpsertResult(incoming.work_id, "created", sorted(incoming.claims), flagged)

    def _find_existing(self, incoming: WorkRecord) -> WorkRecord | None:
        """Exact-identity path of dedup: any shared strong key means the same work."""
        for key in incoming.keys:
            hit = self._index.lookup_key(key)
            if hit and hit != incoming.work_id:
                return self.load(hit)
        # Same work_id but recomputed identity (e.g. a DOI appeared later).
        existing = self.load(incoming.work_id)
        if existing is not None:
            return existing
        return None

    def _absorb(self, target: WorkRecord, incoming: WorkRecord) -> list[str]:
        """Merge claims/manifestations from `incoming` into `target`.

        Returns the field names that gained a new value. Never deletes claims, so
        later disagreement remains detectable.
        """
        added: list[str] = []
        for fname, claims in incoming.claims.items():
            for c in claims:
                if add_claim(target.claims, fname, c.val, src=c.src, ev=c.ev, at=c.at, conf=c.conf):
                    added.append(fname)
        for m in incoming.manifestations:
            target.add_manifestation(m)
        before = dict(target.ids)
        merge_identifiers(target, incoming.keys)
        id_changes = [k for k, v in target.ids.items() if before.get(k) != v]
        # A newly learned stronger key changes the work identity. The previous id must
        # be preserved as an alias, otherwise any id already handed out (in a report, a
        # script, a conversation) stops resolving — silently, since the record simply
        # looks missing.
        strong_new = any(
            key_priority(f"{k}:{v}") < key_priority(target.work_id) for k, v in target.ids.items()
        )
        if strong_new:
            old_path = self.work_path(target.work_id)
            old_wid = target.work_id
            if old_wid and old_wid not in target.aliases:
                target.aliases.append(old_wid)
            target.recompute_identity()
            new_path = self.work_path(target.work_id)
            if old_path.exists() and old_path != new_path:
                new_wid = target.work_id
                self.save(target, log_event="work_reidentified")
                try:
                    old_path.unlink()
                except OSError:
                    pass
                # Drop the old identity's index rows too, or it keeps resolving to a
                # record that is no longer on disk.
                self._index.deindex_work(old_wid, keep_aliases=True)
                self.log(
                    "reidentified",
                    {"from": old_wid, "to": new_wid, "removed_path": old_path.name},
                )
            elif target.work_id != old_wid:
                self.save(target, log_event="work_reidentified")
                self._index.deindex_work(old_wid, keep_aliases=True)
        for f in id_changes:
            if f not in added:
                added.append(f)
        return sorted(set(added))

    def add_manifestation(
        self,
        work_id: str,
        m: Manifestation,
        *,
        log_event: str = "manifestation_added",
    ) -> WorkRecord | None:
        work = self.load(work_id)
        if work is None:
            return None
        merged = work.add_manifestation(m)
        self.save(work, log_event=log_event)
        return work

    def attach_file(
        self,
        work_id: str,
        *,
        channel: str,
        sha256: str,
        rel_path: str,
        size: int,
        external_id: str = "",
        pdf_url: str = "",
        license: str = "",
        kind: str = "record",
    ) -> WorkRecord | None:
        """Record that a PDF now lives in the library for this work."""
        work = self.load(work_id)
        if work is None:
            return None
        target = None
        for m in work.manifestations:
            if external_id and m.external_id == external_id:
                target = m
                break
            if not external_id and m.channel == channel:
                target = m
                break
        if target is None:
            from ..core.ids import compute_manifestation_id

            target = work.add_manifestation(
                Manifestation(
                    mid=compute_manifestation_id(
                        work_id=work_id, channel=channel, external_id=external_id
                    ),
                    channel=channel,
                    kind=kind,
                    external_id=external_id,
                )
            )
        target.pdf_sha256 = sha256
        target.pdf_path = rel_path
        target.pdf_bytes = size
        target.pdf_source = channel
        target.retrieved_at = utc_now()
        if pdf_url:
            target.pdf_url = pdf_url
        if license:
            target.license = license
        self.save(work, log_event="file_attached")
        return work

    def attach_fulltext(self, work_id: str, *, rel_path: str, chars: int, mid: str = "") -> None:
        work = self.load(work_id)
        if work is None:
            return
        target = None
        if mid:
            target = next((m for m in work.manifestations if m.mid == mid), None)
        if target is None:
            target = work.best_pdf() or (work.manifestations[0] if work.manifestations else None)
        if target is None:
            return
        target.fulltext_path = rel_path
        target.fulltext_chars = chars
        self.save(work, log_event="fulltext_attached")

    # ------------------------------------------------------------------ #
    # Dedup
    # ------------------------------------------------------------------ #

    def dedup_candidates(self, work: WorkRecord, *, limit: int = 5) -> list[DedupCandidate]:
        """Fuzzy stage of dedup. Produces candidates; never merges by itself."""
        keys = work.dedup_keys()
        if not keys.title_norm:
            return []
        mine = title_tokens(keys.title_norm)
        out: list[DedupCandidate] = []
        for other in self._dedup_block(keys.year, keys.title_norm, work.work_id):
            other_keys = other.dedup_keys()
            # Shared identifiers already handled by the exact stage; treat any
            # remaining overlap as very strong evidence.
            shared_id = (
                (keys.doi and keys.doi == other_keys.doi)
                or (keys.arxiv and keys.arxiv == other_keys.arxiv)
            )
            theirs = title_tokens(other_keys.title_norm)
            sim = jaccard(mine, theirs)
            if shared_id:
                sim = 1.0
            if sim < MERGE_CANDIDATE_JACCARD:
                continue
            author_match = bool(keys.first_author) and keys.first_author == other_keys.first_author
            year_delta: int | None = None
            if keys.year is not None and other_keys.year is not None:
                year_delta = abs(keys.year - other_keys.year)
            score = sim
            if author_match:
                score = min(1.0, score + 0.03)
            if year_delta == 0:
                score = min(1.0, score + 0.02)
            elif year_delta is not None and year_delta > 2:
                score = max(0.0, score - 0.15)
            reason_bits = [f"title_jaccard={sim:.2f}"]
            if shared_id:
                reason_bits.append("shared_identifier")
            if author_match:
                reason_bits.append("first_author_match")
            if year_delta is not None:
                reason_bits.append(f"year_delta={year_delta}")
            out.append(
                DedupCandidate(
                    other_id=other.work_id,
                    score=score,
                    title_sim=sim,
                    author_match=author_match,
                    year_delta=year_delta,
                    reason=", ".join(reason_bits),
                )
            )
        out.sort(key=lambda c: c.score, reverse=True)
        return out[:limit]

    def _dedup_block(self, year: int | None, title_norm: str, exclude: str) -> list[WorkRecord]:
        """Cheap blocking so dedup does not compare against the whole library."""
        toks = title_norm.split()
        prefixes = [" ".join(toks[:2])] if toks else []
        if len(toks) > 3:
            prefixes.append(" ".join(toks[2:4]))
        years = [year - 1, year, year + 1] if year is not None else [None]
        seen: dict[str, WorkRecord] = {}
        for y in years:
            for p in prefixes:
                if not p:
                    continue
                for wid in self._index.block_members(f"{y or 'x'}|{p}"):
                    if wid == exclude or wid in seen:
                        continue
                    w = self.load(wid)
                    if w is not None:
                        seen[wid] = w
        return list(seen.values())

    def merge(self, keep_id: str, drop_id: str, *, reason: str = "manual") -> dict[str, Any]:
        """Explicitly merge two works. `drop_id` becomes an alias of `keep_id`."""
        keep = self.load(keep_id) or self.resolve(keep_id)
        drop = self.load(drop_id) or self.resolve(drop_id)
        if keep is None or drop is None:
            raise KeyError(f"cannot merge: missing {keep_id!r} or {drop_id!r}")
        if keep.work_id == drop.work_id:
            return {"merged": False, "reason": "same work"}
        # Keep the identity that ranks strongest, so a DOI-bearing record wins over
        # a title-derived one regardless of which side the caller listed first.
        if key_priority(drop.work_id) < key_priority(keep.work_id):
            keep, drop = drop, keep
        added = self._absorb(keep, drop)
        for alias in drop.keys:
            if alias and alias not in keep.aliases:
                keep.aliases.append(alias)
        self.save(keep, log_event="work_merged_manual")
        drop_path = self.work_path(drop.work_id)
        if drop_path.exists():
            try:
                drop_path.unlink()
            except OSError:
                pass
        self._work_cache.pop(drop.work_id, None)
        # Remove the absorbed work from the derived index, keeping its alias rows so
        # the dropped identifier still resolves to the surviving record.
        self._index.deindex_work(drop.work_id, keep_aliases=True)
        self.log("merge", {"keep": keep.work_id, "drop": drop.work_id, "reason": reason,
                           "fields": added})
        return {"merged": True, "keep": keep.work_id, "drop": drop.work_id, "fields": added}

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #

    def search(
        self,
        query: str = "",
        *,
        year_from: int | None = None,
        year_to: int | None = None,
        venue: str = "",
        has_pdf: bool | None = None,
        author: str = "",
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Search the local corpus. Falls back to a scan if the FTS index is unusable."""
        try:
            return self._index.query(
                query,
                year_from=year_from,
                year_to=year_to,
                venue=venue,
                author=author,
                has_pdf=has_pdf,
                limit=limit,
            )
        except sqlite3.OperationalError:
            # An unusable FTS table must not fail the query outright.
            return self._search_like(query, limit, year_from, year_to, venue, author, has_pdf)

    def _search_like(
        self,
        query: str,
        limit: int,
        year_from: int | None,
        year_to: int | None,
        venue: str,
        author: str,
        has_pdf: bool | None,
    ) -> list[dict[str, Any]]:
        needle = query.casefold()
        out: list[dict[str, Any]] = []
        for w in self.iter_works():
            if needle and needle not in (w.title() + " " + w.abstract()).casefold():
                continue
            if year_from is not None and (w.year() or 0) < year_from:
                continue
            if year_to is not None and (w.year() or 0) > year_to:
                continue
            if venue and venue.casefold() not in w.venue().casefold():
                continue
            if author and not any(author.casefold() in a.casefold() for a in w.authors()):
                continue
            if has_pdf is not None and w.has_pdf() != has_pdf:
                continue
            s = w.summary()
            s["local"] = True
            out.append(s)
            if len(out) >= limit:
                break
        return out

    # ------------------------------------------------------------------ #
    # SQLite index (derived, always rebuildable)
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # Stats / export / maintenance
    # ------------------------------------------------------------------ #

    def stats(self) -> dict[str, Any]:
        works = list(self.iter_works())
        years: dict[int, int] = {}
        venues: dict[str, int] = {}
        with_pdf = with_fulltext = 0
        conflicts = 0
        for w in works:
            y = w.year()
            if y:
                years[y] = years.get(y, 0) + 1
            v = w.venue()
            if v:
                venues[v] = venues.get(v, 0) + 1
            if w.has_pdf():
                with_pdf += 1
            if w.has_fulltext():
                with_fulltext += 1
            if any(field_conflict(w.claims, f) for f in ("title", "year", "venue", "doi")):
                conflicts += 1
        bytes_on_disk = 0
        if self.files_dir.exists():
            for p in self.files_dir.glob("**/*"):
                if p.is_file():
                    bytes_on_disk += p.stat().st_size
        return {
            "root": str(self.root),
            "works": len(works),
            "with_pdf": with_pdf,
            "with_fulltext": with_fulltext,
            "pdf_bytes": bytes_on_disk,
            "pdf_mb": round(bytes_on_disk / (1024 * 1024), 2),
            "evidence_snapshots": self.evidence.count(),
            "ledger_events": len(read_jsonl(self.ledger_path)),
            "works_with_conflicts": conflicts,
            "year_range": [min(years), max(years)] if years else None,
            "top_venues": sorted(venues.items(), key=lambda kv: -kv[1])[:10],
            "index_present": self.index_path.exists(),
            "pending_merges": len(self.pending_merges()),
        }

    def pending_merges(self) -> list[dict[str, Any]]:
        """Merge candidates previously flagged, surfaced for explicit decision."""
        out: list[dict[str, Any]] = []
        for ev in self.ledger(event="work_created"):
            for c in ev.get("merge_candidates", []) or []:
                out.append({"work_id": ev.get("work_id", ""), **c})
        return out

    def unresolved_merges(self) -> list[dict[str, Any]]:
        """Pending candidates whose two works still both exist."""
        out = []
        for c in self.pending_merges():
            a, b = c.get("work_id", ""), c.get("other_id", "")
            if a and b and self.load(a) is not None and self.load(b) is not None:
                out.append(c)
        return out

    def export_bibtex(self, work_ids: list[str] | None = None, *, key_style: str = "authorYear") -> str:
        from .cite import to_bibtex

        works = [self.load(w) for w in work_ids] if work_ids else list(self.iter_works())
        entries = [to_bibtex(w, key_style=key_style) for w in works if w is not None]
        return "\n\n".join(e for e in entries if e) + ("\n" if entries else "")

    def store_file(self, data: bytes, *, ext: str = "pdf") -> tuple[str, str, int]:
        """Content-address bytes into `files/`. Identical bytes are stored once.

        Returns (sha256, library-relative path, size).
        """
        digest = sha256_bytes(data)
        rel = Path("files") / digest[:2] / f"{digest}.{ext}"
        abs_path = self.root / rel
        if not abs_path.exists():
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = abs_path.with_suffix(abs_path.suffix + ".part")
            tmp.write_bytes(data)
            os.replace(tmp, abs_path)
        return digest, str(rel).replace("\\", "/"), len(data)

    def store_fulltext(self, work_id: str, text: str) -> tuple[str, int]:
        rel = Path("blobs") / _fs_safe(work_id) / "fulltext.txt"
        abs_path = self.root / rel
        write_text_atomic(abs_path, text)
        return str(rel).replace("\\", "/"), len(text)

    def passages_path(self, work_id: str) -> Path:
        """Absolute path of a work's passage index.

        Exposed because the on-disk name is escaped (a DOI contains "/") and callers
        that reconstruct it by hand get a path that does not exist. Deriving it in one
        place keeps tests, tools and the library agreeing on the layout.
        """
        return self.root / Path("blobs") / _fs_safe(work_id) / "passages.json"

    def store_passages(
        self, work_id: str, passages: list[Any], *, source_sha256: str = ""
    ) -> tuple[str, int]:
        """Persist the passage index for a work, next to its full text.

        Derived from the full text and rebuildable, but stored because rebuilding it on
        every question would mean re-tokenising every paper in the corpus — the same
        "do not redo the work" principle the rest of the tool follows.

        `source_sha256` records which full text this index was built from. Without it,
        re-extracting a PDF would leave a stale passage index in place and searches
        would keep hitting text that is no longer on disk — a derived artefact silently
        disagreeing with its source.
        """
        rel = Path("blobs") / _fs_safe(work_id) / "passages.json"
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

    def read_passages(self, work: WorkRecord) -> list[Any]:
        """Load a work's passages, rebuilding them whenever the source text changed.

        Self-healing rather than strict: a library created before this index existed, or
        one whose passage file was deleted or invalidated by a re-extraction, must still
        be answerable rather than requiring a migration step an agent would have to
        remember.
        """
        from .passages import chunk_text, load_passages

        text = self.read_fulltext(work)
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
            self.store_passages(work.work_id, passages, source_sha256=digest)
        return passages

    def read_fulltext(self, work: WorkRecord) -> str:
        for m in work.manifestations:
            if m.fulltext_path:
                p = self.root / m.fulltext_path
                if p.exists():
                    return p.read_text(encoding="utf-8", errors="replace")
        return ""

    def file_abs(self, rel_path: str) -> Path:
        return self.root / rel_path

    def render_work(self, work: WorkRecord, *, show_claims: bool = False) -> str:
        """Compact text view for terminal/agent consumption."""
        lines = [
            f"{work.work_id}",
            f"  title : {work.title()}",
            f"  authors: {', '.join(work.authors()[:8])}"
            + (" et al." if len(work.authors()) > 8 else ""),
            f"  year  : {work.year()}   venue: {work.venue()}",
        ]
        if work.ids:
            lines.append("  ids   : " + ", ".join(f"{k}={v}" for k, v in sorted(work.ids.items())))
        for m in work.manifestations:
            flag = "PDF" if m.pdf_path else ("pdf_url" if m.pdf_url else "-")
            lines.append(
                f"  [{m.channel}] {m.kind} {m.version or ''} {m.year or ''} -> {flag}"
                + (f" ({m.pdf_bytes} B)" if m.pdf_bytes else "")
            )
        if work.check_status:
            lines.append(f"  check : {work.check_status} {work.check_notes}")
        if show_claims:
            for f in ("title", "year", "venue", "doi"):
                for c in work.claims.get(f, []):
                    lines.append(f"  claim {f} <- {c.src} (ev={c.ev or '-'}): {c.val}")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _fs_safe(work_id: str) -> str:
    """Make an id safe as a filename while staying reversible enough to read."""
    out = work_id.replace("/", "%2F").replace("\\", "%5C").replace(":", "%3A")
    out = out.replace("|", "%7C").replace("<", "%3C").replace(">", "%3E")
    out = out.replace('"', "%22").replace("*", "%2A").replace("?", "%3F")
    return out[:180]


def _sources_of(work: WorkRecord) -> list[str]:
    srcs: list[str] = []
    for claims in work.claims.values():
        for c in claims:
            if c.src not in srcs:
                srcs.append(c.src)
    return srcs


__all__ = [
    "AUTO_MERGE_JACCARD",
    "DEFAULT_LIBRARY_DIRNAME",
    "LIBRARY_SCHEMA",
    "MERGE_CANDIDATE_JACCARD",
    "DedupCandidate",
    "Library",
    "UpsertResult",
    "default_library_root",
]
