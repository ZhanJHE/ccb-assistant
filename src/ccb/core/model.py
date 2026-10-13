"""The canonical record models.

Field-level provenance is the load-bearing idea here. A field is never a single
overwritten value; it is an ordered list of *claims*, each naming the channel that
asserted it, when, and which raw evidence snapshot it came from. Display picks one
claim by an explicit trust rule, but every claim survives — so a disagreement about
a volume number or a year is visible instead of being silently swallowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .ids import (
    Identifier,
    compute_dedup_keys,
    compute_manifestation_id,
    compute_work_id,
    work_id_from_keys,
)
from .util import normalize_arxiv_id, normalize_doi, normalize_url, utc_now

SCHEMA_VERSION = 1

# Fields that carry bibliographic claims and therefore get full provenance.
CLAIM_FIELDS: tuple[str, ...] = (
    "title",
    "abstract",
    "authors",
    "year",
    "venue",
    "venue_type",
    "volume",
    "issue",
    "pages",
    "publisher",
    "doi",
    "arxiv_id",
    "openreview_id",
    "url",
    "pdf_url",
    "oa_status",
    "license",
    "language",
)

# Identifier-ish fields: their values are normalized before being stored.
_ID_FIELDS = {
    "doi": normalize_doi,
    "arxiv_id": normalize_arxiv_id,
    "arxiv": normalize_arxiv_id,
    "url": normalize_url,
}

# Which channel is trusted first when several disagree. Unlisted channels rank last.
# DBLP is the CS authority; publisher-of-record metadata (Crossref) beats
# aggregators; arXiv is authoritative for preprints.
DEFAULT_TRUST: tuple[str, ...] = (
    "crossref",
    "dblp",
    "openreview",
    "arxiv",
    "openalex",
    "europepmc",
    "pubmed",
    "unpaywall",
    "semantic_scholar",
    "paper_search",
    "manual",
)


@dataclass
class Claim:
    """One channel's assertion about one field."""

    src: str
    val: Any
    at: str = field(default_factory=utc_now)
    ev: str = ""  # evidence snapshot id
    conf: float | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"src": self.src, "val": self.val, "at": self.at}
        if self.ev:
            out["ev"] = self.ev
        if self.conf is not None:
            out["conf"] = self.conf
        return out

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Claim":
        return Claim(
            src=d.get("src", "?"),
            val=d.get("val"),
            at=d.get("at", ""),
            ev=d.get("ev", ""),
            conf=d.get("conf"),
        )


def _claim_values_equal(a: Any, b: Any) -> bool:
    """Compare claim values, tolerating list vs scalar and whitespace differences."""
    if isinstance(a, list) or isinstance(b, list):
        la = a if isinstance(a, list) else [a]
        lb = b if isinstance(b, list) else [b]
        if len(la) != len(lb):
            return False
        return all(
            str(x).strip().casefold() == str(y).strip().casefold() for x, y in zip(la, lb)
        )
    return str(a).strip().casefold() == str(b).strip().casefold()


def add_claim(
    claims: dict[str, list[Claim]],
    fieldname: str,
    value: Any,
    *,
    src: str,
    ev: str = "",
    at: str = "",
    conf: float | None = None,
) -> bool:
    """Record a claim. Returns True when the field gained a new distinct value.

    A repeated assertion of an *identical* value from the same source is dropped
    (idempotent re-runs), but the same value from a *different* source is kept —
    that cross-source agreement is what lets us later say "two independent sources
    agree on this year".
    """
    if value is None or value == "" or value == []:
        return False
    norm = _ID_FIELDS.get(fieldname)
    if norm:
        value = norm(str(value))
        if not value:
            return False
    if isinstance(value, str):
        value = value.strip()
    for existing in claims.get(fieldname, []):
        if existing.src == src and _claim_values_equal(existing.val, value):
            return False
    claims.setdefault(fieldname, []).append(
        Claim(src=src, val=value, at=at or utc_now(), ev=ev, conf=conf)
    )
    return True


def resolve_field(
    claims: dict[str, list[Claim]], fieldname: str, trust: Iterable[str] = DEFAULT_TRUST
) -> Any:
    """Pick the display value for a field by source trust order.

    Ties break toward the most recently asserted claim, so a re-verification that
    changed nothing does not reorder anything but a genuine correction wins.
    """
    vals = claims.get(fieldname) or []
    if not vals:
        return None
    order = {name: i for i, name in enumerate(trust)}
    ranked = sorted(
        vals,
        key=lambda c: (order.get(c.src, len(order)), _neg_time(c.at)),
    )
    return ranked[0].val


def _neg_time(ts: str) -> str:
    """Sort helper: later timestamps sort first under ascending order."""
    return "".join(chr(0x10FFFF - ord(c)) if ord(c) < 0x10FFFF else c for c in (ts or ""))


def field_sources(claims: dict[str, list[Claim]], fieldname: str) -> list[str]:
    seen: list[str] = []
    for c in claims.get(fieldname, []):
        if c.src not in seen:
            seen.append(c.src)
    return seen


def field_conflict(claims: dict[str, list[Claim]], fieldname: str) -> bool:
    """True when sources disagree on this field — surfaced, never auto-resolved."""
    vals = claims.get(fieldname) or []
    if len(vals) < 2:
        return False
    first = vals[0].val
    return any(not _claim_values_equal(first, c.val) for c in vals[1:])


# --------------------------------------------------------------------------- #
# Manifestation
# --------------------------------------------------------------------------- #


@dataclass
class Manifestation:
    """One carrier of a work at one channel: a specific record/PDF/version."""

    mid: str
    channel: str
    kind: str = "record"  # record | preprint | proceedings | journal | repository
    external_id: str = ""
    version: str = ""
    venue: str = ""
    year: int | None = None
    url: str = ""
    pdf_url: str = ""
    pdf_sha256: str = ""
    pdf_path: str = ""
    pdf_bytes: int = 0
    pdf_source: str = ""  # channel that actually served the bytes
    fulltext_path: str = ""
    fulltext_chars: int = 0
    license: str = ""
    retrieved_at: str = ""
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        out = {
            "mid": self.mid,
            "channel": self.channel,
            "kind": self.kind,
            "external_id": self.external_id,
            "retrieved_at": self.retrieved_at or utc_now(),
        }
        for k in (
            "version", "venue", "year", "url", "pdf_url", "pdf_sha256",
            "pdf_path", "pdf_source", "fulltext_path", "license", "notes",
        ):
            v = getattr(self, k)
            if v:
                out[k] = v
        if self.pdf_bytes:
            out["pdf_bytes"] = self.pdf_bytes
        if self.fulltext_chars:
            out["fulltext_chars"] = self.fulltext_chars
        return out

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Manifestation":
        m = Manifestation(
            mid=d.get("mid", ""),
            channel=d.get("channel", "?"),
            kind=d.get("kind", "record"),
        )
        for k in (
            "external_id", "version", "venue", "url", "pdf_url", "pdf_sha256",
            "pdf_path", "pdf_source", "fulltext_path", "license", "retrieved_at", "notes",
        ):
            setattr(m, k, d.get(k, "") or "")
        m.year = d.get("year")
        m.pdf_bytes = d.get("pdf_bytes", 0) or 0
        m.fulltext_chars = d.get("fulltext_chars", 0) or 0
        return m


# --------------------------------------------------------------------------- #
# Work
# --------------------------------------------------------------------------- #


@dataclass
class WorkRecord:
    """The authoritative local record for one conceptual paper."""

    work_id: str
    matched_key: str = ""
    ids: dict[str, str] = field(default_factory=dict)
    claims: dict[str, list[Claim]] = field(default_factory=dict)
    manifestations: list[Manifestation] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    checked_at: str = ""
    check_status: str = ""  # "", "ok", "changed", "retracted", "gone"
    check_notes: str = ""
    schema: int = SCHEMA_VERSION
    # Auxiliary, non-bibliographic data attached by a channel (user annotations,
    # migration bookkeeping). Deliberately NOT claims: these have no field-level
    # provenance and no conflict semantics - the newest value simply wins.
    extras: dict[str, Any] = field(default_factory=dict)

    # ---------------- identity ---------------- #

    @property
    def keys(self) -> list[str]:
        """All `scheme:value` keys that identify this work, strongest first."""
        out = [f"{k}:{v}" for k, v in sorted(self.ids.items()) if v]
        if self.work_id:
            out.insert(0, self.work_id)
        for a in self.aliases:
            if a not in out:
                out.append(a)
        return out

    def recompute_identity(self) -> None:
        """Re-derive work_id from the current id set, remembering the old id as alias."""
        new_id, matched = compute_work_id(ids=dict(self.ids))
        if not new_id:
            return
        if self.work_id and new_id != self.work_id and self.work_id not in self.aliases:
            self.aliases.append(self.work_id)
        self.work_id = new_id
        self.matched_key = matched or self.matched_key

    # ---------------- claims ---------------- #

    def title(self) -> str:
        return resolve_field(self.claims, "title") or ""

    def authors(self) -> list[str]:
        val = resolve_field(self.claims, "authors")
        if isinstance(val, list):
            return [str(a) for a in val]
        return [str(val)] if val else []

    def year(self) -> int | None:
        val = resolve_field(self.claims, "year")
        try:
            return int(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    def venue(self) -> str:
        return resolve_field(self.claims, "venue") or ""

    def abstract(self) -> str:
        return resolve_field(self.claims, "abstract") or ""

    def best_pdf(self) -> Manifestation | None:
        """Prefer a manifestation that already has bytes on disk."""
        with_bytes = [m for m in self.manifestations if m.pdf_path]
        if with_bytes:
            # Prefer the published version over a preprint when both are local.
            order = {"proceedings": 0, "journal": 0, "preprint": 1, "repository": 2, "record": 3}
            return sorted(with_bytes, key=lambda m: order.get(m.kind, 9))[0]
        with_url = [m for m in self.manifestations if m.pdf_url]
        return with_url[0] if with_url else None

    def has_fulltext(self) -> bool:
        return any(m.fulltext_path for m in self.manifestations)

    def has_pdf(self) -> bool:
        return bool(self.manifests_with_pdf())

    def manifests_with_pdf(self) -> list[Manifestation]:
        return [m for m in self.manifestations if m.pdf_path]

    # ---------------- mutation ---------------- #

    def add_manifestation(self, m: Manifestation) -> Manifestation:
        """Add or update a manifestation, keyed by mid then (channel, external_id)."""
        for i, existing in enumerate(self.manifestations):
            if existing.mid and existing.mid == m.mid:
                merged = _merge_manifestation(existing, m)
                self.manifestations[i] = merged
                self.updated_at = utc_now()
                return merged
            if (
                existing.channel == m.channel
                and existing.external_id
                and existing.external_id == m.external_id
            ):
                merged = _merge_manifestation(existing, m)
                self.manifestations[i] = merged
                self.updated_at = utc_now()
                return merged
        self.manifestations.append(m)
        self.updated_at = utc_now()
        return m

    def ingest_ids(self, ids: dict[str, str]) -> None:
        for scheme, value in (ids or {}).items():
            if not value:
                continue
            norm = _ID_FIELDS.get(scheme)
            if norm:
                value = norm(str(value))
                if not value:
                    continue
            self.ids.setdefault(scheme, value)

    def dedup_keys(self):
        return compute_dedup_keys(
            title=self.title(),
            authors=self.authors(),
            year=self.year(),
            doi=self.ids.get("doi", ""),
            arxiv=self.ids.get("arxiv", ""),
        )

    # ---------------- serialization ---------------- #

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema": self.schema,
            "work_id": self.work_id,
            "matched_key": self.matched_key,
            "ids": dict(sorted(self.ids.items())),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "claims": {
                k: [c.as_dict() for c in v] for k, v in sorted(self.claims.items()) if v
            },
            "manifestations": [m.as_dict() for m in self.manifestations],
        }
        if self.aliases:
            out["aliases"] = list(self.aliases)
        if self.checked_at:
            out["checked_at"] = self.checked_at
        if self.check_status:
            out["check_status"] = self.check_status
        if self.check_notes:
            out["check_notes"] = self.check_notes
        if self.extras:
            out["extras"] = dict(sorted(self.extras.items()))
        return out

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "WorkRecord":
        w = WorkRecord(
            work_id=d.get("work_id", ""),
            matched_key=d.get("matched_key", ""),
            schema=d.get("schema", SCHEMA_VERSION),
        )
        w.ids = dict(d.get("ids", {}))
        w.aliases = list(d.get("aliases", []))
        w.created_at = d.get("created_at", w.created_at)
        w.updated_at = d.get("updated_at", w.updated_at)
        w.checked_at = d.get("checked_at", "")
        w.check_status = d.get("check_status", "")
        w.check_notes = d.get("check_notes", "")
        w.extras = dict(d.get("extras") or {})
        for fname, clist in (d.get("claims") or {}).items():
            w.claims[fname] = [Claim.from_dict(c) for c in clist]
        w.manifestations = [Manifestation.from_dict(m) for m in d.get("manifestations", [])]
        return w

    # ---------------- views ---------------- #

    def summary(self) -> dict[str, Any]:
        """Compact, agent-facing view: the resolved values plus caveat flags."""
        conflicts = [f for f in CLAIM_FIELDS if field_conflict(self.claims, f)]
        best = self.best_pdf()
        return {
            "work_id": self.work_id,
            "title": self.title(),
            "authors": self.authors(),
            "year": self.year(),
            "venue": self.venue(),
            "doi": self.ids.get("doi", ""),
            "arxiv_id": self.ids.get("arxiv", ""),
            "openreview_id": self.ids.get("openreview", ""),
            "ids": dict(sorted(self.ids.items())),
            "manifestations": len(self.manifestations),
            "has_pdf": bool(best and best.pdf_path),
            "has_fulltext": self.has_fulltext(),
            "pdf_path": best.pdf_path if best else "",
            "field_sources": {
                f: field_sources(self.claims, f)
                for f in ("title", "year", "venue", "doi")
                if self.claims.get(f)
            },
            "conflicts": conflicts,
            "check_status": self.check_status,
        }


def _merge_manifestation(old: Manifestation, new: Manifestation) -> Manifestation:
    """Fill blanks on `old` from `new` without clobbering known-good local facts."""
    for k in (
        "external_id", "version", "venue", "url", "pdf_url", "pdf_sha256",
        "pdf_path", "pdf_source", "fulltext_path", "license", "notes",
    ):
        if not getattr(old, k) and getattr(new, k):
            setattr(old, k, getattr(new, k))
    if old.year is None and new.year is not None:
        old.year = new.year
    if not old.pdf_bytes and new.pdf_bytes:
        old.pdf_bytes = new.pdf_bytes
    if not old.fulltext_chars and new.fulltext_chars:
        old.fulltext_chars = new.fulltext_chars
    if old.kind in ("", "record") and new.kind and new.kind != "record":
        old.kind = new.kind
    old.retrieved_at = new.retrieved_at or old.retrieved_at or utc_now()
    return old


# --------------------------------------------------------------------------- #
# Channel output
# --------------------------------------------------------------------------- #


@dataclass
class DedupCandidate:
    """One fuzzy-dedup hit: who it looks like, how strongly, and why."""

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


@dataclass
class ChannelRecord:
    """A normalized record as emitted by a channel, before it enters the library."""

    channel: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    venue_type: str = ""
    abstract: str = ""
    doi: str = ""
    arxiv_id: str = ""
    openreview_id: str = ""
    acl_id: str = ""
    pmlr: str = ""
    dblp_key: str = ""
    pmid: str = ""
    openalex_id: str = ""
    url: str = ""
    pdf_url: str = ""
    oa_status: str = ""
    license: str = ""
    language: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    publisher: str = ""
    kind: str = "record"
    version: str = ""
    ev: str = ""  # evidence snapshot id this record was parsed from
    extras: dict[str, Any] = field(default_factory=dict)

    def ids(self) -> dict[str, str]:
        return {
            "doi": self.doi,
            "arxiv": self.arxiv_id,
            "openreview": self.openreview_id,
            "acl": self.acl_id,
            "pmlr": self.pmlr,
            "dblp": self.dblp_key,
            "pmid": self.pmid,
            "openalex": self.openalex_id,
            "url": self.url,
        }

    def to_work(self) -> WorkRecord:
        """Build a fresh WorkRecord carrying field-level provenance for every value."""
        ids = {k: v for k, v in self.ids().items() if v}
        work_id, matched = compute_work_id(
            ids=ids, title=self.title, authors=self.authors, year=self.year
        )
        if not work_id:
            raise ValueError(f"channel {self.channel!r} produced a record with no identity")
        w = WorkRecord(work_id=work_id, matched_key=matched)
        w.ingest_ids(ids)
        for fname in CLAIM_FIELDS:
            value = getattr(self, fname, None)
            if value in (None, "", []):
                continue
            add_claim(w.claims, fname, value, src=self.channel, ev=self.ev)
        # Auxiliary data rides along; dropping it here would silently discard user
        # annotations on every ingest (found the hard way during the migration).
        w.extras.update(self.extras)
        m = Manifestation(
            mid=compute_manifestation_id(
                work_id=work_id,
                channel=self.channel,
                external_id=self._external_id(),
                version=self.version,
                venue=self.venue,
                year=self.year,
            ),
            channel=self.channel,
            kind=self.kind,
            external_id=self._external_id(),
            version=self.version,
            venue=self.venue,
            year=self.year,
            url=self.url,
            pdf_url=self.pdf_url,
            license=self.license,
        )
        w.add_manifestation(m)
        return w

    def _external_id(self) -> str:
        return (
            self.doi
            or self.arxiv_id
            or self.openreview_id
            or self.dblp_key
            or self.acl_id
            or self.pmlr
            or self.pmid
            or ""
        )


def key_priority(key: str) -> int:
    """Rank of a `scheme:value` key; lower is stronger. Unknown schemes rank last."""
    from .ids import KEY_CHAIN

    scheme = key.split(":", 1)[0]
    try:
        return KEY_CHAIN.index(scheme)
    except ValueError:
        return len(KEY_CHAIN)


def strongest_key(keys: Iterable[str]) -> str:
    ranked = sorted((k for k in keys if k), key=key_priority)
    return ranked[0] if ranked else ""


def merge_identifiers(target: WorkRecord, keys: list[str]) -> None:
    """Fold `scheme:value` keys into a record's id map (first value per scheme wins)."""
    for key in keys:
        if ":" not in key:
            continue
        scheme, _, value = key.partition(":")
        if scheme in _ID_FIELDS:
            value = _ID_FIELDS[scheme](value)
        if not value:
            continue
        target.ids.setdefault(scheme, value)


__all__ = [
    "CLAIM_FIELDS",
    "DEFAULT_TRUST",
    "SCHEMA_VERSION",
    "ChannelRecord",
    "Claim",
    "Manifestation",
    "WorkRecord",
    "add_claim",
    "field_conflict",
    "field_sources",
    "key_priority",
    "merge_identifiers",
    "resolve_field",
    "strongest_key",
    "work_id_from_keys",
    "Identifier",
]
