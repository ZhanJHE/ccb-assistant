"""The channel abstraction — the search module's single front door.

A *channel* is any source of paper records or files: a free HTTP API, a keyed
commercial API, an MCP server, a local CLI tool, or a human dropping in a PDF.

The whole point of this layer is **transparency**: the caller asks for papers and
does not care which channel answered, whether it needed a key, or whether it
degraded. Concretely:

* a channel that needs a missing credential does not fail the request — it reports
  itself as unavailable, naming the variable, and the others carry on;
* a channel that breaks does not abort a fan-out — its failure is recorded and
  returned alongside the successes;
* every network call is snapshotted to `evidence/` before parsing, so a record can
  always be traced to the bytes that produced it.

Adding a channel is therefore a data problem, not a control-flow problem: implement
`search` and/or `lookup` and declare the spec.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from ...library.evidence import EvidenceStore
from ...core.model import ChannelRecord
from ..net import Http, Response, credential, mailto
from ...core.util import utc_now, write_json_atomic

# Capability flags.
CAP_SEARCH = "search"
CAP_LOOKUP = "lookup"
CAP_PDF = "pdf"
CAP_OA_RESOLVE = "oa_resolve"
CAP_FULLTEXT = "fulltext"
CAP_CITATIONS = "citations"
CAP_VENUE = "venue"
CAP_BIBTEX = "bibtex"


@dataclass
class ChannelSpec:
    """Declarative description of a channel. Drives routing, reporting and safety."""

    name: str
    kind: str = "http"  # http | cli | mcp | manual
    title: str = ""
    caps: tuple[str, ...] = ()
    auth: str = "none"  # "none" | "env:VAR" | "env:VAR?" (optional)
    license: str = ""
    rate_rps: float = 1.0
    cs_authority: bool = False
    notes: str = ""
    requires_network: bool = True
    enabled: bool = True
    disabled_reason: str = ""
    config: dict[str, Any] = field(default_factory=dict)

    def required_env(self) -> list[str]:
        """Environment variables this channel needs, excluding optional ones."""
        if not self.auth.startswith("env:"):
            return []
        var = self.auth[4:]
        if var.endswith("?"):
            return []
        return [var]

    def optional_env(self) -> list[str]:
        if not self.auth.startswith("env:"):
            return []
        var = self.auth[4:]
        return [var[:-1]] if var.endswith("?") else []

    def credential_ok(self) -> bool:
        return all(bool(credential(v)) for v in self.required_env())

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "caps": list(self.caps),
            "auth": self.auth,
            "rate_rps": self.rate_rps,
            "enabled": self.enabled,
        }
        for k in ("title", "license", "notes", "disabled_reason"):
            if getattr(self, k):
                out[k] = getattr(self, k)
        if self.cs_authority:
            out["cs_authority"] = True
        req = self.required_env()
        opt = self.optional_env()
        if req:
            out["needs_env"] = req
            out["env_ready"] = all(bool(credential(v)) for v in req)
        if opt:
            out["optional_env"] = opt
        return out


@dataclass
class ChannelResult:
    """Outcome of one channel operation. Failures travel with successes."""

    channel: str
    records: list[ChannelRecord] = field(default_factory=list)
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    total_available: int | None = None
    queries: list[dict[str, Any]] = field(default_factory=list)
    ev_id: str = ""
    elapsed_ms: int = 0

    @property
    def ok(self) -> bool:
        return not self.error

    def as_dict(self, *, with_records: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {
            "channel": self.channel,
            "ok": self.ok,
            "count": len(self.records),
        }
        if self.total_available is not None:
            out["total_available"] = self.total_available
        if self.error:
            out["error"] = self.error
        if self.warnings:
            out["warnings"] = self.warnings
        if self.ev_id:
            out["ev"] = self.ev_id
        if with_records:
            out["records"] = [r.__dict__ for r in self.records]
        return out


class Channel:
    """Base class. Subclasses implement `search` and/or `lookup`."""

    #: Every concrete channel declares its descriptor. The base class carries a
    #: placeholder so that a channel whose module forgot to set one still constructs
    #: and reports itself as usable-but-unnamed, rather than raising
    #: `AttributeError` deep inside `__init__` where the cause is invisible.
    spec: ChannelSpec = ChannelSpec(
        name="unnamed",
        kind="http",
        title="Unnamed channel",
        notes="This channel did not declare a spec; it should not be used directly.",
        enabled=False,
        disabled_reason="channel did not declare a spec",
    )

    def __init__(
        self,
        *,
        http: Http | None = None,
        evidence: EvidenceStore | None = None,
        verbose: bool = False,
    ):
        self.http = http or Http(host_rates={self.spec.name: self.spec.rate_rps})
        self.evidence = evidence
        self.verbose = verbose
    # ---------------- capabilities ---------------- #

    def has(self, cap: str) -> bool:
        return cap in self.spec.caps

    # Identifier schemes this channel can resolve. Declared so the orchestrator can
    # skip a channel rather than pay for a request whose only possible answer is
    # "wrong kind of identifier" — an arXiv id should never be sent to a DOI-only
    # resolver, and doing so wastes a call and pollutes the error report.
    supports: tuple[str, ...] = ()

    def supports_identifier(self, scheme: str) -> bool:
        """True when this channel can act on an identifier scheme.

        An empty `supports` means "no opinion" and the channel is always tried.
        """
        if not self.supports:
            return True
        return scheme in self.supports

    # ------------------------------------------------------------------ #
    # Identifier verification  ← the guard against silently wrong answers
    # ------------------------------------------------------------------ #

    def verify_identifier(
        self, identifier: str, records: list[ChannelRecord]
    ) -> tuple[list[ChannelRecord], list[str]]:
        """Keep only records that actually carry the identifier we asked about.

        This exists because a search index can answer a precise-looking query with an
        unrelated paper. Measured example: OpenAlex's
        ``filter=doi:10.48550/arxiv.1706.03762`` returns ``count=1`` for a work whose
        own DOI is ``10.65215/2q58a426`` and whose title merely coincides. Accepting
        that record silently attaches a wrong DOI to the requested paper — the single
        worst failure mode for a library whose whole value is trustworthy identity.

        Records for identifiers that cannot be checked (a bare title, a URL) pass
        through untouched, and the reason for any rejection is returned so the caller
        can report it rather than wonder why a lookup came back empty.
        """
        from ...core.ids import parse_identifier

        parsed = parse_identifier(identifier)
        if parsed is None or parsed.scheme in ("title", "url", ""):
            return records, []
        kept: list[ChannelRecord] = []
        rejected: list[str] = []
        for rec in records:
            ok, why = self._record_carries(parsed.scheme, parsed.value, rec)
            if ok:
                kept.append(rec)
            else:
                rejected.append(
                    f"discarded a record that does not carry {parsed.scheme}:{parsed.value} "
                    f"({why})"
                )
        return kept, rejected

    def _record_carries(
        self, scheme: str, value: str, rec: ChannelRecord
    ) -> tuple[bool, str]:
        from ...core.util import normalize_acl_id, normalize_doi, normalize_pmlr

        if scheme == "doi":
            got = normalize_doi(rec.doi)
            if got == normalize_doi(value):
                return True, ""
            # An arXiv preprint is legitimately reachable by its registered arXiv DOI.
            from ...core.util import arxiv_doi

            if rec.arxiv_id and arxiv_doi(rec.arxiv_id) == normalize_doi(value):
                return True, ""
            return False, f"record DOI is {got or 'absent'}"
        if scheme == "arxiv":
            from ...core.util import normalize_arxiv_id

            got = normalize_arxiv_id(rec.arxiv_id)
            if got and got == normalize_arxiv_id(value):
                return True, ""
            # A published version may carry the arXiv DOI instead of the id field.
            from ...core.util import arxiv_doi

            if normalize_doi(rec.doi) == arxiv_doi(value):
                return True, ""
            return False, f"record arXiv id is {got or 'absent'}"
        if scheme == "openreview":
            return (
                (True, "")
                if rec.openreview_id and rec.openreview_id.casefold() == value.casefold()
                else (False, f"record OpenReview id is {rec.openreview_id or 'absent'}")
            )
        if scheme == "acl":
            got = normalize_acl_id(rec.acl_id)
            return (
                (True, "")
                if got and got == normalize_acl_id(value)
                else (False, f"record ACL id is {got or 'absent'}")
            )
        if scheme == "pmlr":
            got = normalize_pmlr(rec.pmlr)
            return (
                (True, "")
                if got and got == normalize_pmlr(value)
                else (False, f"record PMLR ref is {got or 'absent'}")
            )
        if scheme == "pmid":
            return (
                (True, "")
                if rec.pmid and rec.pmid == value
                else (False, f"record PMID is {rec.pmid or 'absent'}")
            )
        if scheme == "dblp":
            return (
                (True, "")
                if rec.dblp_key and rec.dblp_key.casefold() == value.casefold()
                else (False, f"record dblp key is {rec.dblp_key or 'absent'}")
            )
        if scheme == "openalex":
            got = str(rec.openalex_id or "")
            got = got.rsplit("/", 1)[-1]
            return (
                (True, "")
                if got and got.casefold() == value.casefold()
                else (False, f"record OpenAlex id is {got or 'absent'}")
            )
        return True, ""

    @property
    def name(self) -> str:
        return self.spec.name

    def available(self) -> tuple[bool, str]:
        """(usable, reason). Missing credentials degrade rather than raise."""
        if not self.spec.enabled:
            return False, self.spec.disabled_reason or "disabled by configuration"
        if not self.spec.credential_ok():
            missing = ", ".join(self.spec.required_env())
            return False, f"missing credential: {missing}"
        return True, ""

    # ---------------- operations ---------------- #

    def search(self, query: str, *, limit: int = 10, year_from: int | None = None,
               year_to: int | None = None, **kw: Any) -> ChannelResult:
        return ChannelResult(self.name, error="this channel does not support search")

    def lookup(self, identifier: str, **kw: Any) -> ChannelResult:
        return ChannelResult(self.name, error="this channel does not support lookup")

    def download_pdf(self, rec: ChannelRecord, **kw: Any) -> tuple[bytes, str, str]:
        """Fetch a PDF. Returns (bytes, final_pdf_url, error). Default: use pdf_url."""
        if not rec.pdf_url:
            return b"", "", "record has no pdf_url"
        data, resp = self.http.download(rec.pdf_url)
        from ..net import pdf_rejection_reason

        reason = pdf_rejection_reason(data, resp)
        if reason:
            return b"", rec.pdf_url, reason
        return data, rec.pdf_url, ""

    def check(self, rec: ChannelRecord) -> dict[str, Any]:
        """Re-verification hook: report retraction/version/OA changes. Optional."""
        return {"channel": self.name, "status": "unsupported"}

    def describe(self) -> dict[str, Any]:
        usable, reason = self.available()
        d = self.spec.as_dict()
        d["usable"] = usable
        if not usable:
            d["unavailable_reason"] = reason
        return d

    # ---------------- helpers for subclasses ---------------- #

    def snapshot(
        self,
        *,
        url: str = "",
        params: dict[str, Any] | None = None,
        status: int = 0,
        content_type: str = "",
        body: str = "",
        command: list[str] | None = None,
        error: str = "",
        notes: str = "",
    ) -> str:
        """Persist raw evidence and return its id. No-op when no store is attached."""
        if self.evidence is None:
            return ""
        ev = self.evidence.record(
            channel=self.name,
            kind=self.spec.kind,
            url=url,
            params=params,
            status=status,
            content_type=content_type,
            body=body,
            command=command,
            error=error,
            notes=notes,
        )
        return ev.ev_id

    def request_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
        data: bytes | None = None,
        notes: str = "",
    ) -> tuple[Any | None, Response, str]:
        """GET+parse JSON and snapshot the raw body. Returns (parsed, response, ev_id)."""
        resp = self.http.request(url, method=method, params=params, headers=headers, data=data)
        ev_id = self.snapshot(
            url=resp.url or url,
            params=params,
            status=resp.status,
            content_type=resp.content_type,
            body=resp.body,
            error=resp.error,
            notes=notes,
        )
        if not resp.ok:
            return None, resp, ev_id
        from ..net import challenge_reason, is_bot_challenge

        if is_bot_challenge(resp.body, resp.content_type):
            resp.error = challenge_reason(resp.body, resp.content_type)
            return None, resp, ev_id
        try:
            return resp.json(), resp, ev_id
        except ValueError as exc:
            resp.error = str(exc)
            return None, resp, ev_id

    def request_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        accept: str = "text/plain, */*",
        notes: str = "",
    ) -> tuple[str, Response, str]:
        resp = self.http.request(url, params=params, headers=headers, accept=accept)
        ev_id = self.snapshot(
            url=resp.url or url,
            params=params,
            status=resp.status,
            content_type=resp.content_type,
            body=resp.body,
            error=resp.error,
            notes=notes,
        )
        return resp.body, resp, ev_id

    def polite_params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Params that put us in a vendor's polite pool, when we have an address."""
        params: dict[str, Any] = {}
        addr = mailto()
        if addr:
            params["mailto"] = addr
        params.update(extra or {})
        return params

    @staticmethod
    def make_record(channel: str, **fields: Any) -> ChannelRecord:
        fields.pop("channel", None)
        return ChannelRecord(channel=channel, **fields)

    # ---------------- misc ---------------- #

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Channel {self.name} kind={self.spec.kind}>"


class ManualChannel(Channel):
    """A channel backed by a user-provided file instead of a network service.

    Registered so that `kind: manual` in the descriptor language is real and a
    user-supplied PDF enters the same pipeline (and gets the same library record)
    as anything fetched over the network.
    """

    spec = ChannelSpec(
        name="manual",
        kind="manual",
        title="User-supplied file or metadata",
        caps=(CAP_PDF,),
        auth="none",
        license="n/a",
        requires_network=False,
        notes="Records and PDFs supplied directly by the user.",
    )

    def download_pdf(self, rec: ChannelRecord, **kw: Any) -> tuple[bytes, str, str]:
        return b"", "", "manual channel: supply the file with `ccb add-file`"
