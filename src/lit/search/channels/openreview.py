"""OpenReview API v2 — the closest thing CS has to an authoritative conference feed.

Why this channel matters more than its size suggests: OpenReview is where ICLR,
NeurIPS and ACL submissions, reviews and decisions actually live, and those papers
frequently have **no DOI**. Everything else in the ecosystem keys identity on DOI or
arXiv id, so these records get unstable, title-derived identities. OpenReview's own
note id is a stable identifier, which makes it a first-class part of the identity
chain rather than an afterthought.

Shape notes:
* the v2 API nests every field as ``{"value": ...}``;
* ``content.pdf`` is a *relative* path (``/pdf/<hash>.pdf``) that must be joined to
  the API host, not treated as an absolute URL;
* ``count`` is a large sentinel (10000) rather than a real total, so it must not be
  reported as a result count.
"""

from __future__ import annotations

import re
from typing import Any

from ...core.model import ChannelRecord
from ...core.util import strip_latex
from .base import (
    CAP_BIBTEX,
    CAP_LOOKUP,
    CAP_PDF,
    CAP_SEARCH,
    CAP_VENUE,
    Channel,
    ChannelResult,
    ChannelSpec,
)

API = "https://api2.openreview.net"
HOST = "https://openreview.net"

# Search returns everything on OpenReview (including reviews and replies), so
# submissions have to be filtered to notes that actually carry a title + authors.
_SUBMISSION_HINTS = ("/Submission", "/Blind_Submission", "/Poster", "/Oral", "/Spotlight")


class OpenReviewChannel(Channel):
    supports = ("openreview", "title")

    spec = ChannelSpec(
        name="openreview",
        kind="http",
        title="OpenReview (ICLR / NeurIPS / ACL submissions and decisions)",
        caps=(CAP_SEARCH, CAP_LOOKUP, CAP_PDF, CAP_VENUE, CAP_BIBTEX),
        auth="none",
        license="Per-venue terms; most OpenReview content is openly readable",
        rate_rps=1.0,
        cs_authority=True,
        notes=(
            "The stable identity source for CS conference papers that have no DOI. "
            "Search covers all note types, so results are filtered to submissions "
            "with a title and author list; reviews and replies are excluded."
        ),
    )

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        year_from: int | None = None,
        year_to: int | None = None,
        **kw: Any,
    ) -> ChannelResult:
        # Over-fetch: many search hits are reviews/replies that get filtered out.
        fetch = max(10, min(limit * 4, 100))
        data, resp, ev_id = self.request_json(
            f"{API}/notes/search",
            params={"term": query, "limit": fetch, "content": "all", "group": "all",
                    "source": "forum"},
            notes="openreview search",
        )
        res = ChannelResult(
            self.name,
            ev_id=ev_id,
            queries=[{"url": f"{API}/notes/search", "params": {"term": query, "limit": fetch}}],
        )
        if data is None:
            res.error = resp.error or f"HTTP {resp.status}"
            return res
        notes = data.get("notes") if isinstance(data, dict) else None
        if not isinstance(notes, list):
            res.error = "openreview response has no 'notes' list"
            return res
        for n in notes:
            rec = self._parse_note(n, ev_id)
            if rec is None:
                continue
            y = rec.year
            if year_from and y and y < year_from:
                continue
            if year_to and y and y > year_to:
                continue
            res.records.append(rec)
            if len(res.records) >= limit:
                break
        if not res.records:
            res.warnings.append(
                "no OpenReview submissions matched (the search endpoint also returns "
                "reviews/replies, which are filtered out here)"
            )
        return res

    def lookup(self, identifier: str, **kw: Any) -> ChannelResult:
        from ...core.ids import parse_identifier

        parsed = parse_identifier(identifier)
        if parsed is None or parsed.scheme != "openreview":
            return ChannelResult(
                self.name,
                error=f"not an OpenReview id: {identifier!r} (expected e.g. 'openreview:abcDEF123')",
            )
        data, resp, ev_id = self.request_json(
            f"{API}/notes", params={"id": parsed.value}, notes="openreview lookup-id"
        )
        res = ChannelResult(
            self.name, ev_id=ev_id, queries=[{"url": f"{API}/notes", "params": {"id": parsed.value}}]
        )
        if data is None:
            res.error = resp.error or f"HTTP {resp.status}"
            return res
        notes = data.get("notes") if isinstance(data, dict) else None
        if not isinstance(notes, list) or not notes:
            res.error = "no OpenReview note with that id"
            return res
        rec = self._parse_note(notes[0], ev_id)
        if rec is None:
            res.error = "the OpenReview note carries no usable bibliographic fields"
            return res
        res.records.append(rec)
        return res

    # ------------------------------------------------------------------ #

    def _parse_note(self, note: dict[str, Any], ev_id: str) -> ChannelRecord | None:
        if not isinstance(note, dict):
            return None
        content = note.get("content") or {}
        if not isinstance(content, dict):
            return None
        title = strip_latex(_val(content, "title")).strip()
        title = re.sub(r"\s+", " ", title)
        authors = [a for a in _val(content, "authors", []) if isinstance(a, str)]
        if not title or not authors:
            # Reviews, replies and decisions have no title/authors — skip them.
            return None
        note_id = note.get("id") or ""
        forum = note.get("forum") or note_id
        venue = _val(content, "venue") or ""
        venueid = _val(content, "venueid") or ""
        year = _year_from(venue, venueid, note)
        pdf_rel = _val(content, "pdf") or ""
        pdf_url = ""
        if pdf_rel:
            pdf_url = pdf_rel if pdf_rel.startswith("http") else f"{HOST}{pdf_rel}"
        if not pdf_url and forum:
            pdf_url = f"{HOST}/pdf/{forum}.pdf"
        abstract = strip_latex(_val(content, "abstract") or "").strip()
        invitations = note.get("invitations") or []
        return ChannelRecord(
            channel=self.name,
            title=title,
            authors=authors,
            year=year,
            venue=venue or _venue_from_id(venueid) or "OpenReview",
            venue_type="conference",
            abstract=abstract,
            openreview_id=note_id,
            url=f"{HOST}/forum?id={forum}",
            pdf_url=pdf_url,
            oa_status="green" if pdf_url else "",
            license=note.get("license") or "",
            language="en",
            kind="proceedings",
            ev=ev_id,
            extras={
                "forum": forum,
                "venueid": venueid,
                "invitations": [i for i in invitations if isinstance(i, str)][:4],
                "is_submission": any(
                    isinstance(i, str) and any(h in i for h in _SUBMISSION_HINTS)
                    for i in invitations
                ),
            },
        )


def _val(content: dict[str, Any], key: str, default: Any = "") -> Any:
    """Read a v2 content field, which is wrapped as {'value': ...}."""
    entry = content.get(key)
    if isinstance(entry, dict):
        return entry.get("value", default)
    if entry is None:
        return default
    return entry


def _year_from(venue: str, venueid: str, note: dict[str, Any]) -> int | None:
    for text in (venue, venueid):
        m = re.search(r"(19|20)\d{2}", text or "")
        if m:
            return int(m.group(0))
    # cdate/tcdate are epoch milliseconds.
    for key in ("cdate", "tcdate", "pdate", "odate"):
        v = note.get(key)
        if isinstance(v, int) and v > 0:
            import datetime

            try:
                return datetime.datetime.fromtimestamp(
                    v / 1000, tz=datetime.timezone.utc
                ).year
            except (OverflowError, OSError, ValueError):
                continue
    return None


def _venue_from_id(venueid: str) -> str:
    """Turn 'ICLR.cc/2024/Conference' into 'ICLR 2024'."""
    if not venueid:
        return ""
    parts = [p for p in venueid.split("/") if p and not p.endswith(".cc")]
    if not parts:
        return ""
    head = parts[0]
    year = next((p for p in parts if re.fullmatch(r"(19|20)\d{2}", p)), "")
    if "Conference" in parts and not year:
        for p in parts:
            m = re.search(r"(19|20)\d{2}", p)
            if m:
                year = m.group(0)
                break
    return f"{head} {year}".strip()
