"""Identity-based dedup: find who an incoming record already is.

Split out of store.py: the scoring and lookup policy (exact key chains, blocking,
Jaccard) is one decision point, separate from the write path that absorbs a match.
Methods run under the caller's lock. The thresholds are injected by the Library
(they are store policy, not dedup mechanics).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..core.model import DedupCandidate, WorkRecord
from ..core.util import jaccard, title_tokens

if TYPE_CHECKING:  # pragma: no cover
    from .store import Library


class DedupEngine:
    """Exact-identity and fuzzy-bounded lookup for incoming records."""

    def __init__(self, lib: "Library", *, auto_merge: float, candidate: float):
        self._lib = lib
        self.auto_merge = auto_merge
        self.candidate = candidate

    def find_existing(self, incoming: WorkRecord) -> WorkRecord | None:
        """Exact-identity path of dedup: any shared strong key means the same work."""
        for key in incoming.keys:
            hit = self._lib._index.lookup_key(key)
            if hit and hit != incoming.work_id:
                return self._lib.load(hit)
        # Same work_id but recomputed identity (e.g. a DOI appeared later).
        existing = self._lib.load(incoming.work_id)
        if existing is not None:
            return existing
        return None

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
            if sim < self.candidate:
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
                for wid in self._lib._index.block_members(f"{y or 'x'}|{p}"):
                    if wid == exclude or wid in seen:
                        continue
                    w = self._lib.load(wid)
                    if w is not None:
                        seen[wid] = w
        return list(seen.values())
