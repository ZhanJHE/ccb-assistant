"""Search and download — the local-first acquisition protocol.

This module is where the tool's reason for existing actually happens:

    get(identifier)
        hit = library.resolve(identifier)      # local, zero network
        if hit is complete:  return it         # nothing is re-fetched, re-parsed
        else:                fetch only what is missing, then return

The important consequence is that asking about the same paper a second time costs
nothing: no search, no download, no extraction, no re-reading. And asking about a
*related* paper reuses everything already known, because channel fan-out is
deduplicated into the same library as it goes.

Every operation here is idempotent. Re-running `get` on a complete record is a no-op
by design, because an agent that repeats a step must not corrupt the corpus.

This module owns the channel registry and is the one place that writes to the
library. Grounded retrieval and text extraction are *reads* of the corpus, so they
live in ``ccb.library.retrieve``; the two thin delegations on the Resolver class
below exist only so a caller holding a Resolver need not also hold a Library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from ..core.model import ChannelRecord, Manifestation, WorkRecord
from ..library import Library
from ..library.retrieve import ask as _ask_impl
from ..library.retrieve import extract_into as _extract_impl
from .channels.base import CAP_LOOKUP, CAP_PDF, Channel, ChannelResult
from .channels.registry import Registry

# How many channels must succeed before we stop fanning out on a lookup. Stopping as
# soon as a *definitive* identifier is in hand (DOI / OpenReview id) is the meaningful
# signal; a bare title match is not, so it does not end the fan-out.
STOP_AFTER_LOOKUP_SUCCESS = 2


def _has_definitive_identifier(records: list[ChannelRecord]) -> bool:
    for rec in records:
        if rec.doi or rec.openreview_id or rec.pmlr or rec.acl_id:
            return True
    return False


@dataclass
class AcquireResult:
    """Outcome of `get`: what was found, and precisely what had to be done."""

    work_id: str
    source: str  # "local" | "channels" | "local+channels" | "none"
    work: WorkRecord | None = None
    actions: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.work is not None

    def as_dict(self, *, full: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "work_id": self.work_id,
            "source": self.source,
            "ok": self.ok,
            "actions": self.actions,
        }
        if self.errors:
            out["errors"] = self.errors
        if self.warnings:
            out["warnings"] = self.warnings
        if self.message:
            out["message"] = self.message
        if self.work is not None:
            out["record"] = self.work.summary() if not full else self.work.as_dict()
        return out


@dataclass
class FindResult:
    """Outcome of `find`: local hits first, then channel hits, already deduplicated."""

    query: str
    local_hits: list[dict[str, Any]] = field(default_factory=list)
    fetched: list[dict[str, Any]] = field(default_factory=list)
    channels_queried: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    ingested: int = 0
    merge_candidates: list[dict[str, Any]] = field(default_factory=list)
    local_answered: bool = False
    stopped_early: bool = False
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "query": self.query,
            "local_answered": self.local_answered,
            "local_hits": self.local_hits,
            "fetched": self.fetched,
            "channels_queried": self.channels_queried,
            "ingested": self.ingested,
        }
        if self.errors:
            out["errors"] = self.errors
        if self.warnings:
            out["warnings"] = self.warnings
        if self.merge_candidates:
            out["merge_candidates"] = self.merge_candidates
        if self.stopped_early:
            out["stopped_early"] = True
        if self.message:
            out["message"] = self.message
        return out


class Resolver:
    """Ties the channel registry to the library and enforces local-first."""

    def __init__(self, library: Library, registry: Registry, *, offline: bool = False,
                 verbose: bool = False):
        self.library = library
        self.registry = registry
        self.offline = offline
        self.verbose = verbose

    # ------------------------------------------------------------------ #
    # get
    # ------------------------------------------------------------------ #

    def get(
        self,
        identifier: str,
        *,
        with_pdf: bool = False,
        refresh: bool = False,
        channels: str = "",
        extract: bool = False,
    ) -> AcquireResult:
        """Resolve an identifier, using the network only for what is actually missing.

        `refresh` forces a re-query even on a local hit — used by `check`, not by
        normal reads, because the whole point is to avoid re-querying.

        `extract` stores the full text of any PDF that is present but unextracted. The
        CLI turns this on when a PDF was just downloaded: paying for the bytes and then
        not making them readable would leave the corpus useless offline.
        """
        local = None if refresh else self.library.resolve(identifier)
        errors: dict[str, str] = {}
        warnings: list[str] = []
        actions: list[str] = []

        if local is None and self.offline:
            return AcquireResult(
                work_id="",
                source="none",
                errors={"offline": "not in the local library, and --offline forbids the network"},
                message=(
                    "Nothing to fetch: this identifier is not in the local library and "
                    "offline mode is on."
                ),
            )

        # Decide whether metadata actually needs to come from the network. A local
        # record that already holds a title plus a stable identifier is complete; the
        # only remaining gap can be the full text, which is handled separately below.
        # Getting this wrong is what makes a "local-first" tool quietly re-query every
        # time, so it is expressed as an explicit predicate rather than a list of
        # conditions that `--with-pdf` can accidentally override.
        needs_metadata = local is None or refresh or not _metadata_is_complete(local)

        fetched_any = False
        if needs_metadata:
            fan = self._fan_out_lookup(identifier, channels=channels)
            errors.update(fan["errors"])
            warnings.extend(fan["warnings"])
            if fan["records"]:
                fetched_any = True
                for rec in fan["records"]:
                    upsert = self.library.upsert_record(rec)
                    if upsert.merge_candidates:
                        warnings.append(
                            f"{rec.channel}: {len(upsert.merge_candidates)} possible duplicate(s) "
                            "recorded for review (not merged)"
                        )
                    local = self.library.load(upsert.work_id) or local
                    actions.append(f"metadata from {rec.channel}")

        if local is None:
            return AcquireResult(
                work_id="",
                source="none",
                errors=errors,
                warnings=warnings,
                message=(
                    "Could not resolve this identifier through any available channel. "
                    "See errors for which channels were tried and why they failed."
                ),
            )

        source = "local+channels" if fetched_any else "local"

        # Full text is fetched only when it is wanted and genuinely absent.
        if with_pdf and not local.has_pdf():
            dl = self._fetch_pdf(local)
            errors.update(dl["errors"])
            warnings.extend(dl["warnings"])
            if dl["actions"]:
                actions.extend(dl["actions"])
                # Store the text immediately: downloading a PDF and leaving it
                # unextracted means `open` cannot answer offline, which defeats the
                # point of having downloaded it.
                extract = True

        if extract and not local.has_fulltext():
            ex = self._extract_text(local)
            if ex.get("chars"):
                actions.append(f"full text extracted ({ex['chars']} chars via {ex.get('engine')})")
            elif ex.get("error"):
                warnings.append(f"text extraction: {ex['error']}")
            local = self.library.load(local.work_id) or local

        if local is not None and (with_pdf or extract):
            source = "local+channels" if fetched_any else "local"

        message = _acquire_message(local, actions, errors, fetched_any)
        return AcquireResult(
            work_id=local.work_id,
            source=source,
            work=local,
            actions=actions,
            errors=errors,
            warnings=warnings,
            message=message,
        )

    def _fan_out_lookup(
        self, identifier: str, *, channels: str, conditional: bool = False
    ) -> dict[str, Any]:
        if self.offline:
            return {"records": [], "errors": {"offline": "network access disabled"}, "warnings": []}
        from ..core.ids import parse_identifier

        parsed = parse_identifier(identifier)
        scheme = parsed.scheme if parsed is not None else ""
        usable = [
            c for c in self.registry.usable(CAP_LOOKUP)
            if not channels or c.name.casefold() in {
                s.strip().casefold() for s in channels.split(",") if s.strip()
            }
        ]
        unknown = self.registry.unknown_names(channels)
        warnings: list[str] = []
        if unknown:
            warnings.append(f"unknown channel name(s) ignored: {', '.join(unknown)}")
        # Skip channels that cannot act on this identifier scheme: sending an arXiv id
        # to a DOI-only resolver costs a request and can only ever return an error.
        inapplicable = [c.name for c in usable if not c.supports_identifier(scheme)]
        usable = [c for c in usable if c.supports_identifier(scheme)]
        if inapplicable:
            warnings.append(
                f"skipped (cannot resolve a {scheme or 'bare'} identifier): "
                f"{', '.join(inapplicable)}"
            )
        # CS authorities first, so a stable conference identity is learned before an
        # aggregator's weaker record lands.
        usable.sort(key=lambda c: (0 if c.spec.cs_authority else 1, c.spec.name))
        records: list[ChannelRecord] = []
        errors: dict[str, str] = {}
        successes = 0
        not_modified: list[str] = []
        for chan in usable:
            try:
                # A conditional re-check asks the source "changed?" first; channels that
                # cannot answer conditionally fall back to a full lookup.
                res = (
                    chan.lookup_conditional(identifier)
                    if conditional
                    else chan.lookup(identifier)
                )
            except Exception as exc:
                errors[chan.name] = f"{type(exc).__name__}: {exc}"
                continue
            if res.not_modified:
                not_modified.append(chan.name)
                continue
            if res.error:
                errors[chan.name] = res.error
            # Central guard: never let a record into the library that does not actually
            # carry the identifier we asked about.
            records_before = len(res.records)
            kept, rejected = chan.verify_identifier(identifier, res.records)
            if rejected:
                res.records = kept
                warnings.extend(f"{chan.name}: {r}" for r in rejected)
                if records_before and not kept:
                    errors.setdefault(
                        chan.name,
                        "returned a record for the wrong paper; discarded rather than "
                        "stored (the source's identifier index disagrees with its own "
                        "record)",
                    )
            warnings.extend(f"{chan.name}: {w}" for w in res.warnings)
            if res.records:
                records.extend(res.records)
                successes += 1
            if records and (
                _has_definitive_identifier(records) or successes >= STOP_AFTER_LOOKUP_SUCCESS
            ):
                break
        # Channels that could not run at all are reported, not silently skipped.
        tried = {c.name for c in usable}
        for chan in self.registry.all():
            if chan.name in tried:
                continue
            ok, reason = chan.available()
            if not ok and chan.has(CAP_LOOKUP) and chan.supports_identifier(scheme):
                errors.setdefault(chan.name, reason)
        return {
            "records": records,
            "errors": errors,
            "warnings": warnings,
            # Every channel that answered did so with a 304: the sources vouch the work
            # is unchanged, and `check` reports that without a diff.
            "not_modified_all": bool(not_modified) and not records and not errors,
            "not_modified": not_modified,
        }

    def _extract_text(self, work: WorkRecord) -> dict[str, Any]:
        """Extract and store full text for a work that already has a local PDF.

        Thin delegation; the implementation is ``ccb.library.retrieve.extract_into``.
        """
        return _extract_impl(self.library, work)

    # ------------------------------------------------------------------ #
    # grounded retrieval (delegated to the library)
    # ------------------------------------------------------------------ #

    def ask(
        self,
        query: str,
        *,
        limit: int = 5,
        work_ids: Iterable[str] | None = None,
        max_per_work: int = 2,
        passages_around: int = 0,
        section: str = "",
    ) -> dict[str, Any]:
        """Retrieve the passages that answer a query, with checkable citations.

        Thin delegation; the implementation is ``ccb.library.retrieve.ask``. Retrieval
        is a read of the corpus and never touches the network, so it does not belong to
        this module.
        """
        return _ask_impl(
            self.library,
            query,
            limit=limit,
            work_ids=work_ids,
            max_per_work=max_per_work,
            passages_around=passages_around,
            section=section,
        )

    def _fetch_pdf(self, work: WorkRecord) -> dict[str, Any]:
        """Try every channel that can serve a PDF for this work, legally."""
        actions: list[str] = []
        errors: dict[str, str] = {}
        warnings: list[str] = []
        if self.offline:
            return {"actions": actions, "errors": {"offline": "network access disabled"},
                    "warnings": warnings}

        # Build candidate (channel, record) pairs. The work's existing manifestations
        # are the best source of a pdf_url, but a freshly created work may have none
        # with a URL while the record itself does — so every PDF-capable channel also
        # gets a chance to propose a URL from the identifiers we hold.
        candidates: list[tuple[Channel, ChannelRecord]] = []
        seen_channels: set[str] = set()
        for m in work.manifestations:
            chan = self.registry.get(m.channel)
            if chan is None:
                continue
            rec = _record_from_manifestation(work, m)
            if not rec.pdf_url:
                continue
            candidates.append((chan, rec))
            seen_channels.add(chan.name)
        for chan in self.registry.usable(CAP_PDF):
            if chan.name in seen_channels:
                continue
            rec = _record_from_work(work, chan.name)
            if rec.pdf_url:
                candidates.append((chan, rec))
        # An arXiv id is itself a durable open-access locator: derive the canonical PDF
        # URL rather than relying on whichever record happened to carry one.
        arxiv_id = work.ids.get("arxiv", "")
        if arxiv_id:
            arxiv_chan = self.registry.get("arxiv")
            if arxiv_chan is not None and arxiv_chan.available()[0]:
                from ..core.model import ChannelRecord as _CR

                candidates.append(
                    (
                        arxiv_chan,
                        _CR(
                            channel="arxiv",
                            title=work.title(),
                            authors=work.authors(),
                            year=work.year(),
                            arxiv_id=arxiv_id,
                            pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
                            kind="preprint",
                        ),
                    )
                )

        for chan, rec in candidates:
            try:
                data, final_url, err = chan.download_pdf(rec)
            except Exception as exc:
                errors[chan.name] = f"{type(exc).__name__}: {exc}"
                continue
            if err or not data:
                errors[chan.name] = err or "no data"
                continue
            from .net import looks_like_pdf

            if not looks_like_pdf(data):
                errors[chan.name] = "downloaded payload is not a PDF"
                continue
            digest, rel, size = self.library.store_file(data, ext="pdf")
            self.library.attach_file(
                work.work_id,
                channel=chan.name,
                sha256=digest,
                rel_path=rel,
                size=size,
                external_id=rec.extras.get("native_id", "") or _external_id_of(rec),
                pdf_url=final_url or rec.pdf_url,
                license=rec.license,
                kind=rec.kind,
            )
            actions.append(f"pdf via {chan.name} ({size} bytes)")
            break
        else:
            if not candidates:
                warnings.append(
                    "no channel offered an open-access PDF for this work; the record is "
                    "stored without full text (no paywall circumvention is attempted)"
                )
        return {"actions": actions, "errors": errors, "warnings": warnings}

    # ------------------------------------------------------------------ #
    # find
    # ------------------------------------------------------------------ #

    def find(
        self,
        query: str,
        *,
        limit: int = 10,
        channels: str = "",
        year_from: int | None = None,
        year_to: int | None = None,
        local_first: bool = True,
        ingest: bool = True,
        min_local: int = 0,
        stop_after: int = 0,
    ) -> FindResult:
        """Search locally first; only go to the network when the local corpus is thin.

        ``stop_after`` caps the fan-out at N channels that actually produced records
        (0 = query every usable channel). It exists because breadth and politeness are in
        tension on a broad query, and the caller is the one who knows which it needs.
        """
        result = FindResult(query=query)
        local_hits = self.library.search(
            query, limit=max(limit, min_local or 0), year_from=year_from, year_to=year_to
        )
        result.local_hits = local_hits

        if local_first and len(local_hits) >= max(limit, min_local):
            result.local_answered = True
            result.message = (
                f"Answered from the local library ({len(local_hits)} hits); no channel was "
                "queried, so nothing was re-downloaded or re-parsed."
            )
            return result

        if self.offline:
            result.local_answered = True
            result.message = (
                f"Offline mode: returned {len(local_hits)} local hit(s) without querying "
                "channels."
            )
            result.channels_queried = []
            return result

        usable = self.registry.search_channels(channels)
        unknown = self.registry.unknown_names(channels)
        if unknown:
            result.warnings.append(f"unknown channel name(s) ignored: {', '.join(unknown)}")
        result.channels_queried = []
        if not usable:
            result.warnings.append(
                "no search-capable channel is currently available; see `ccb channels`"
            )

        seen_keys: set[str] = set(k["work_id"] for k in local_hits)
        queried: list[str] = []
        productive = 0
        for chan in usable:
            queried.append(chan.name)
            before = len(result.fetched)
            try:
                res: ChannelResult = chan.search(
                    query, limit=limit, year_from=year_from, year_to=year_to
                )
            except Exception as exc:
                result.errors[chan.name] = f"{type(exc).__name__}: {exc}"
                continue
            if res.error:
                result.errors[chan.name] = res.error
            result.warnings.extend(f"{chan.name}: {w}" for w in res.warnings)
            # One lock, one corpus-state write for the whole channel: `upsert_record` is
            # itself serialised, so without this outer hold each record ended its own
            # outermost mutation and the library re-scanned itself once per record — the
            # network call stays outside the lock, only the ingest is inside it.
            with self.library.locked():
                for rec in res.records:
                    if not ingest:
                        result.fetched.append(_unattached(rec))
                        continue
                    upsert = self.library.upsert_record(rec)
                    for cand in upsert.merge_candidates:
                        result.merge_candidates.append({"work_id": upsert.work_id, **cand})
                    result.ingested += 1
                    if upsert.work_id in seen_keys:
                        continue
                    seen_keys.add(upsert.work_id)
                    w = self.library.load(upsert.work_id)
                    if w is not None:
                        entry = w.summary()
                        entry["found_via"] = rec.channel
                        result.fetched.append(entry)
            if len(result.fetched) > before:
                productive += 1
                if stop_after and productive >= stop_after:
                    result.stopped_early = True
                    remaining = len(usable) - len(queried)
                    if remaining:
                        result.warnings.append(
                            f"stopped after {productive} channel(s) produced records "
                            f"(--stop-after {stop_after}); {remaining} channel(s) were not "
                            "queried"
                        )
                    break
        # Filled as channels were actually called: on an early stop the list must name
        # what was queried, not what was available.
        result.channels_queried = queried
        if not result.fetched and not local_hits:
            result.message = (
                "No results. Check the per-channel errors: a keyed or gated channel may "
                "have failed rather than genuinely having nothing."
            )
        return result

    # ------------------------------------------------------------------ #
    # verification (incremental re-check)
    # ------------------------------------------------------------------ #

    def check(self, work_ids: Iterable[str] | None = None, *, limit: int = 0) -> dict[str, Any]:
        """Re-verify stored records against the decisive endpoints.

        Only *identifiers* are re-sent, never whole searches, so this is cheap enough
        to run over a library. The honest output is three-valued: a change was found,
        nothing was found, or the check could not be performed — absence of a
        retraction notice is reported as "not found in the sources checked", because
        claiming "not retracted" from a miss would be a fabrication.
        """
        targets = list(work_ids) if work_ids else [w.work_id for w in self.library.iter_works()]
        if limit:
            targets = targets[:limit]
        report: dict[str, Any] = {
            "checked": 0,
            "changed": [],
            "unchanged": [],
            "unverifiable": [],
            "errors": {},
        }
        for wid in targets:
            work = self.library.load(wid)
            if work is None:
                report["errors"][wid] = "not in the local library"
                continue
            report["checked"] += 1
            outcome = self._check_one(work)
            if outcome["status"] == "changed":
                report["changed"].append({"work_id": wid, **outcome})
            elif outcome["status"] == "unverifiable":
                report["unverifiable"].append({"work_id": wid, **outcome})
            else:
                report["unchanged"].append({"work_id": wid, **outcome})
        return report

    def _check_one(self, work: WorkRecord) -> dict[str, Any]:
        keys = [k for k in work.keys if k.split(":", 1)[0] in
                ("doi", "arxiv", "openreview", "pmid", "dblp", "acl", "pmlr")]
        if not keys:
            return {"status": "unverifiable", "reason": "record has no resolvable identifier"}
        # The strongest key, not whichever the record happened to list first: `work.keys`
        # puts the work_id itself at the front, so taking keys[0] re-checked a dblp- or
        # acl-keyed work against dblp (gated) and reported it unverifiable while Crossref
        # was available the whole time.
        from ..core.ids import work_id_from_keys

        key, _ = work_id_from_keys(keys)
        if not key:
            return {"status": "unverifiable", "reason": "record has no resolvable identifier"}
        before = work.summary()
        fan = self._fan_out_lookup(key, channels="", conditional=True)
        if not fan["records"] and fan.get("not_modified_all"):
            return {
                "status": "unchanged",
                "note": (
                    "every applicable source answered HTTP 304 (not modified since the "
                    f"last check): {', '.join(fan['not_modified'])}"
                ),
            }
        # Only compare fields that should be stable across sources.
        fresh_fields: dict[str, Any] = {}
        for rec in fan["records"]:
            for fname in ("title", "year", "venue", "doi"):
                val = getattr(rec, fname, None)
                if val not in (None, "", []):
                    fresh_fields.setdefault(fname, val)
        if not fresh_fields:
            return {
                "status": "unverifiable",
                "reason": "no channel returned a record for this identifier",
                "errors": fan["errors"],
            }
        for rec in fan["records"]:
            self.library.upsert_record(rec)
        after_work = self.library.load(work.work_id) or work
        after_work.checked_at = _now()
        changed_fields = []
        for fname, val in fresh_fields.items():
            if fname == "year":
                old = before.get("year")
            elif fname == "title":
                old = before.get("title")
            elif fname == "venue":
                old = before.get("venue")
            else:
                old = before.get("doi")
            if old and str(old).strip().casefold() != str(val).strip().casefold():
                changed_fields.append({"field": fname, "was": old, "now": val})
        after_work.check_status = "changed" if changed_fields else "ok"
        # Attribute the difference to the channels that *supplied* the new value. The
        # note used to name `fan['errors'].keys()` — the channels that failed, which is
        # the opposite of what a reader of the provenance needs.
        sources: list[str] = []
        for rec in fan["records"]:
            ch = str(getattr(rec, "channel", "") or "")
            if ch and ch not in sources:
                sources.append(ch)
        after_work.check_notes = (
            f"{len(changed_fields)} field difference(s) vs "
            f"{', '.join(sources) or 'the sources checked'}"
            if changed_fields
            else "consistent with the sources checked"
        )
        self.library.save(after_work, log_event="checked")
        if changed_fields:
            self.library.log("check_changed", {"work_id": after_work.work_id,
                                               "changes": changed_fields})
            return {"status": "changed", "changes": changed_fields, "errors": fan["errors"]}
        return {"status": "unchanged", "note": "no differences found in the sources checked"}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _now() -> str:
    from ..core.util import utc_now

    return utc_now()


def _metadata_is_complete(work: WorkRecord | None) -> bool:
    """A record worth answering from without re-querying the network.

    Requires a title and at least one stable identifier. Abstract, venue and page
    details are *not* required: they can be absent for legitimate reasons (a venue
    paper with no DOI), and treating their absence as "incomplete" would send the tool
    back to the network forever on records that will never improve.
    """
    if work is None:
        return False
    if not work.title():
        return False
    stable = ("doi", "arxiv", "openreview", "acl", "pmlr", "dblp", "pmid", "openalex")
    return any(work.ids.get(k) for k in stable)


def _external_id_of(rec: ChannelRecord) -> str:
    return (
        rec.doi or rec.arxiv_id or rec.openreview_id or rec.dblp_key
        or rec.acl_id or rec.pmlr or rec.pmid or ""
    )


def _record_from_manifestation(work: WorkRecord, m: Manifestation) -> ChannelRecord:
    return ChannelRecord(
        channel=m.channel,
        title=work.title(),
        authors=work.authors(),
        year=m.year or work.year(),
        venue=m.venue or work.venue(),
        doi=work.ids.get("doi", ""),
        arxiv_id=work.ids.get("arxiv", ""),
        openreview_id=work.ids.get("openreview", ""),
        url=m.url,
        pdf_url=m.pdf_url,
        license=m.license,
        kind=m.kind,
        version=m.version,
        extras={"native_id": m.external_id},
    )


def _record_from_work(work: WorkRecord, channel: str) -> ChannelRecord:
    best = work.best_pdf()
    return ChannelRecord(
        channel=channel,
        title=work.title(),
        authors=work.authors(),
        year=work.year(),
        venue=work.venue(),
        doi=work.ids.get("doi", ""),
        arxiv_id=work.ids.get("arxiv", ""),
        openreview_id=work.ids.get("openreview", ""),
        pdf_url=best.pdf_url if best else "",
        kind=best.kind if best else "record",
        extras={},
    )


def _unattached(rec: ChannelRecord) -> dict[str, Any]:
    return {
        "channel": rec.channel,
        "title": rec.title,
        "authors": rec.authors,
        "year": rec.year,
        "venue": rec.venue,
        "doi": rec.doi,
        "arxiv_id": rec.arxiv_id,
        "openreview_id": rec.openreview_id,
        "url": rec.url,
        "pdf_url": rec.pdf_url,
        "ingested": False,
    }


def _acquire_message(
    work: WorkRecord, actions: list[str], errors: dict[str, str], fetched: bool
) -> str:
    if not actions:
        return (
            f"Answered from the local library: {work.title()[:90]!r}. No network call was "
            "needed."
        )
    bits = [f"Stored/updated {work.work_id}."]
    if fetched:
        bits.append("Metadata came from channels: " + "; ".join(actions) + ".")
    if errors:
        bits.append(
            "Unavailable or failing channels: "
            + "; ".join(f"{k}: {v}" for k, v in errors.items())
            + "."
        )
    return " ".join(bits)
