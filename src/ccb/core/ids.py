"""Stable local identities.

Two layers, both deterministic pure functions:

  work_id        conceptual layer — "which paper is this"
  manifestation  carrier layer    — arXiv v1/v2, conference version, journal version

The design goal is *explainability over cleverness*. A work identity is produced by
an explicit, ordered key chain; whichever key matched is recorded, so any work_id
can always be traced back to the evidence that produced it. No probabilistic
entity resolution sits in the identity path — that only ever produces candidates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .util import (
    normalize_arxiv_id,
    normalize_doi,
    normalize_title,
    short_hash,
    title_tokens,
)

# --------------------------------------------------------------------------- #
# Identifier parsing
# --------------------------------------------------------------------------- #

# Ordered by specificity: check DOI first so an arXiv DOI is not misread as an
# arXiv ID, and an ACL Anthology DOI ("10.18653/v1/...") keeps its DOI identity.
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
_ARXIV_MODERN_RE = re.compile(r"\b(\d{4}\.\d{4,5})(v\d+)?\b")
_ARXIV_LEGACY_RE = re.compile(r"\b([a-z-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?\b")
_OPENREVIEW_RE = re.compile(r"\b([A-Za-z0-9_\-]{3,})\b")
_PMID_RE = re.compile(r"\b(?:pmid:)?(\d{7,9})\b", re.IGNORECASE)


@dataclass(frozen=True)
class Identifier:
    """A parsed external identifier."""

    scheme: str  # doi | arxiv | openreview | pmid | dblp | acl | pmlr | url | title
    value: str  # normalized value
    raw: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.scheme}:{self.value}"

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"scheme": self.scheme, "value": self.value}
        if self.extra:
            out["extra"] = dict(self.extra)
        return out


def parse_identifier(text: str) -> Identifier | None:
    """Parse a user-supplied identifier into a typed Identifier.

    Accepts DOI, arXiv ID (either form), arXiv DOI, OpenReview id, PMID, DBLP key,
    ACL Anthology id, PMLR volume/page, or a bare URL. Returns None when nothing
    recognizable is present.
    """
    if not text or not text.strip():
        return None
    raw = text.strip()

    # arXiv DOI must be recognized as arXiv, not as a plain DOI, so that the
    # preprint keeps its preprint identity.
    m = re.search(r"10\.48550/arxiv\.([^\s\"<>]+)", raw, re.IGNORECASE)
    if m:
        aid = normalize_arxiv_id(m.group(1))
        if aid:
            return Identifier("arxiv", aid, raw=raw)

    m = _DOI_RE.search(raw)
    if m:
        doi = normalize_doi(m.group(0).rstrip(".,;)"))
        if doi:
            return Identifier("doi", doi, raw=raw)

    # Explicit scheme prefixes take precedence over pattern guessing.
    low = raw.casefold()
    for prefix in ("arxiv:", "openreview:", "dblp:", "acl:", "pmid:", "openalex:", "pmlr:"):
        if low.startswith(prefix):
            value = raw[len(prefix):].strip()
            scheme = prefix[:-1]
            if scheme == "arxiv":
                value = normalize_arxiv_id(value)
            if value:
                return Identifier(scheme, value, raw=raw)

    m = _ARXIV_MODERN_RE.search(raw)
    if m:
        return Identifier("arxiv", m.group(1), raw=raw)

    m = _ARXIV_LEGACY_RE.search(raw)
    if m:
        return Identifier("arxiv", m.group(1), raw=raw)

    # URL: keep the host+path as a low-confidence identity.
    if raw.startswith(("http://", "https://")):
        return Identifier("url", raw, raw=raw)

    # OpenReview ids look like "abcDEF123" or "NeurIPS-2021-abc".
    m = re.match(r"^[A-Za-z][A-Za-z0-9_\-]{5,}$", raw)
    if m and any(c.isdigit() for c in raw) and not raw.isdigit():
        return Identifier("openreview", raw, raw=raw)

    m = _PMID_RE.match(raw)
    if m:
        return Identifier("pmid", m.group(1), raw=raw)

    return None


# --------------------------------------------------------------------------- #
# Work identity
# --------------------------------------------------------------------------- #

# The key chain. Order is part of the contract: earlier keys are more authoritative
# and more globally unique. Changing this order changes existing work_ids, so it is
# versioned in library.json and treated as a schema migration.
KEY_CHAIN: tuple[str, ...] = (
    "doi",
    "openreview",
    "arxiv",
    "acl",
    "pmlr",
    "dblp",
    "pmid",
    "openalex",
    "url",
    "title",
)

KEY_CHAIN_VERSION = 1


def _title_fallback_key(title: str, authors: list[str] | None, year: int | None) -> str:
    """Last-resort deterministic key for items with no usable identifier.

    Deliberately built from normalized title + first-author surname + year rather
    than a raw title hash, so that trivial punctuation/case differences and the
    presence or absence of a subtitle separator do not fork the identity.
    """
    from .util import first_author_key

    norm = normalize_title(title)
    if not norm:
        return ""
    return f"{norm}|{first_author_key(authors)}|{year or ''}"


def compute_work_id(
    *,
    ids: dict[str, str] | None = None,
    title: str = "",
    authors: list[str] | None = None,
    year: int | None = None,
) -> tuple[str, str]:
    """Return (work_id, matched_key_name).

    The second element is the explainability record: it says which key in the chain
    produced this identity, and is persisted so the decision can be audited.

    One deliberate exception: an arXiv *DOI* (``10.48550/arxiv.<id>``) does not win the
    DOI slot. It is a derived form of the arXiv id, so letting it take precedence made
    the identity of a preprint depend on which channel happened to supply a DOI — the
    same paper stored as ``arxiv:X`` via one route and ``doi:10.48550/arxiv.X`` via
    another. The DOI is still recorded in the id map; it just cannot outrank the
    native identifier it was minted from.
    """
    ids = {k: v for k, v in (ids or {}).items() if v}
    arxiv_id = normalize_arxiv_id(ids.get("arxiv") or "")
    doi = normalize_doi(ids.get("doi") or "")
    if doi.startswith("10.48550/arxiv.") and not arxiv_id:
        # Only an arXiv DOI is known; recover the native id from it.
        arxiv_id = normalize_arxiv_id(doi)
        ids.setdefault("arxiv", arxiv_id)
    for name in KEY_CHAIN:
        if name == "title":
            continue
        if name == "doi" and doi.startswith("10.48550/arxiv."):
            continue
        if name == "arxiv" and arxiv_id:
            return f"arxiv:{arxiv_id}", "arxiv"
        value = ids.get(name)
        if value:
            scheme = "arxiv" if name == "arxiv" else name
            return f"{scheme}:{value}", name
    fallback = _title_fallback_key(title, authors, year)
    if fallback:
        return f"t:{fallback}", "title"
    return "", ""


def work_id_from_keys(keys: list[str]) -> tuple[str, str]:
    """Compute the identity of a work from a list of `scheme:value` strings."""
    best_rank = len(KEY_CHAIN)
    best: tuple[str, str] | None = None
    for key in keys:
        if ":" not in key:
            continue
        scheme, _, value = key.partition(":")
        scheme = {"doi": "doi", "arxiv": "arxiv", "openreview": "openreview",
                  "acl": "acl", "pmlr": "pmlr", "dblp": "dblp", "pmid": "pmid",
                  "openalex": "openalex", "url": "url", "title": "title"}.get(scheme, scheme)
        if scheme in KEY_CHAIN:
            rank = KEY_CHAIN.index(scheme)
            if rank < best_rank:
                best_rank = rank
                best = (f"{scheme}:{value}", scheme)
    if best:
        return best
    return "", ""


def work_path_shard(work_id: str) -> str:
    """Two-level shard so a large library does not put 100k files in one directory."""
    h = short_hash(work_id, length=4)
    return f"{h[:2]}/{h[2:4]}"


# --------------------------------------------------------------------------- #
# Manifestation identity
# --------------------------------------------------------------------------- #


def compute_manifestation_id(
    *,
    work_id: str,
    channel: str,
    external_id: str = "",
    version: str = "",
    venue: str = "",
    year: int | None = None,
) -> str:
    """Identity of one carrier of a work (a specific PDF/record at a specific source).

    Distinguishes arXiv v2 from v3 from the NeurIPS camera-ready, each with its own
    artifacts and page numbering, while all belonging to the same work.
    """
    basis = f"{work_id}\x1f{channel}\x1f{external_id}\x1f{version}\x1f{venue}\x1f{year or ''}"
    return f"m_{short_hash(basis, length=12)}"


# --------------------------------------------------------------------------- #
# Dedup keys
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DedupKeys:
    """Typed container for the comparison keys used by the fuzzy dedup stage."""

    title_norm: str
    title_token_key: str
    first_author: str
    year: int | None
    doi: str = ""
    arxiv: str = ""

    def blocking_key(self) -> str:
        """Cheap blocking key to avoid O(n^2) comparisons across the whole library.

        Buckets by (year +/- 1 is handled by the caller emitting two keys) and the
        first two title tokens, which is stable against word order changes later in
        the title but brittle if the first words differ — hence two buckets.
        """
        toks = self.title_norm.split()[:2]
        return f"{self.year or 'x'}|{' '.join(toks)}"


def compute_dedup_keys(
    *,
    title: str,
    authors: list[str] | None = None,
    year: int | None = None,
    doi: str = "",
    arxiv: str = "",
) -> DedupKeys:
    from .util import first_author_key

    norm = normalize_title(title)
    toks = sorted(title_tokens(title))
    return DedupKeys(
        title_norm=norm,
        title_token_key=" ".join(toks[:24]),
        first_author=first_author_key(authors),
        year=year,
        doi=normalize_doi(doi),
        arxiv=normalize_arxiv_id(arxiv),
    )
