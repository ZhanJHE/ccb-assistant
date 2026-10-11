"""Raw evidence snapshots (snapshot-first).

Every channel call writes its raw response here *before* anything is parsed. That
single decision buys four things at once:

  1. field-level provenance becomes free — a claim points at the bytes that
     produced it;
  2. offline replay and index rebuilds work without re-hitting the network;
  3. multi-source disagreements keep their full context instead of collapsing to
     one overwritten value;
  4. incremental re-verification becomes a diff against stored evidence.

Snapshots are content-addressed, so re-fetching identical bytes is free and two
channels returning the same payload share one file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.util import json_dumps, read_json, sha256_text, utc_now, write_json_atomic, write_text_atomic

# Bodies larger than this are stored as a sidecar file and referenced by hash,
# so a single huge response cannot bloat one JSON document past usefulness.
INLINE_BODY_LIMIT = 256 * 1024

# Never persist these, ever. Credentials travel in query strings for some APIs,
# which means the URL itself is a secret and must be redacted before storage.
_SECRET_PARAM_KEYS = ("api_key", "apikey", "key", "token", "access_token", "email", "mailto",
                      "password", "secret", "authorization")


def redact_url(url: str) -> str:
    """Redact credential-bearing query parameters from a URL.

    Several scholarly APIs authenticate by query string, so the URL *is* a
    credential. Redaction happens at write time, not display time, so a secret can
    never reach disk in the first place.
    """
    if not url:
        return ""
    if "?" not in url:
        return url
    base, _, query = url.partition("?")
    parts: list[str] = []
    for chunk in query.split("&"):
        if not chunk:
            continue
        name, sep, _value = chunk.partition("=")
        if name.casefold() in _SECRET_PARAM_KEYS:
            parts.append(f"{name}{sep or '='}<redacted>")
        else:
            parts.append(chunk)
    return f"{base}?{'&'.join(parts)}"


def redact_mapping(values: dict[str, Any] | None) -> dict[str, Any]:
    """Redact credential-bearing keys from a parameter mapping."""
    if not values:
        return {}
    out: dict[str, Any] = {}
    for k, v in values.items():
        out[k] = "<redacted>" if k.casefold() in _SECRET_PARAM_KEYS else v
    return out


@dataclass
class Evidence:
    """Metadata for one stored raw response."""

    ev_id: str
    channel: str
    kind: str  # "http" | "cli" | "mcp" | "manual"
    url: str = ""
    params: dict[str, Any] | None = None
    status: int = 0
    content_type: str = ""
    retrieved_at: str = ""
    body_sha256: str = ""
    body_chars: int = 0
    body: str = ""
    body_path: str = ""
    command: list[str] | None = None
    error: str = ""
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ev_id": self.ev_id,
            "channel": self.channel,
            "kind": self.kind,
            "retrieved_at": self.retrieved_at or utc_now(),
            "body_sha256": self.body_sha256,
            "body_chars": self.body_chars,
        }
        for k in ("url", "content_type", "command", "error", "notes", "body_path"):
            v = getattr(self, k)
            if v:
                out[k] = v
        if self.status:
            out["status"] = self.status
        if self.params:
            out["params"] = redact_mapping(self.params)
        if self.body and not self.body_path:
            out["body"] = self.body
        return out

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Evidence":
        e = Evidence(
            ev_id=d.get("ev_id", ""),
            channel=d.get("channel", "?"),
            kind=d.get("kind", "http"),
        )
        for k in ("url", "content_type", "retrieved_at", "body_sha256", "body",
                  "body_path", "error", "notes"):
            setattr(e, k, d.get(k, "") or "")
        e.params = d.get("params") or {}
        e.command = d.get("command")
        e.status = d.get("status", 0) or 0
        e.body_chars = d.get("body_chars", 0) or 0
        return e


class EvidenceStore:
    """Directory-backed store of raw response snapshots."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, ev_id: str) -> Path:
        return self.root / f"{ev_id}.json"

    def _body_path(self, ev_id: str) -> Path:
        return self.root / f"{ev_id}.body"

    @staticmethod
    def make_id(channel: str, discriminator: str) -> str:
        return f"ev_{channel}_{sha256_text(discriminator)[:12]}"

    def record(
        self,
        *,
        channel: str,
        kind: str = "http",
        url: str = "",
        params: dict[str, Any] | None = None,
        status: int = 0,
        content_type: str = "",
        body: str = "",
        command: list[str] | None = None,
        error: str = "",
        notes: str = "",
        ev_id: str = "",
    ) -> Evidence:
        """Persist one raw response. Returns the Evidence handle with its id set."""
        safe_url = redact_url(url)
        if not ev_id:
            disc = safe_url or " ".join(command or []) or body[:200]
            ev_id = self.make_id(channel, disc)
        ev = Evidence(
            ev_id=ev_id,
            channel=channel,
            kind=kind,
            url=safe_url,
            params=redact_mapping(params),
            status=status,
            content_type=content_type,
            retrieved_at=utc_now(),
            body_sha256=sha256_text(body) if body else "",
            body_chars=len(body or ""),
            command=list(command) if command else None,
            error=error,
            notes=notes,
        )
        if len(body or "") > INLINE_BODY_LIMIT:
            write_text_atomic(self._body_path(ev_id), body)
            ev.body_path = str(self._body_path(ev_id).name)
        else:
            ev.body = body or ""
        write_json_atomic(self._path(ev_id), ev.as_dict())
        return ev

    def get(self, ev_id: str) -> Evidence | None:
        d = read_json(self._path(ev_id))
        if d is None:
            return None
        ev = Evidence.from_dict(d)
        if ev.body_path:
            bpath = self.root / ev.body_path
            if bpath.exists():
                ev.body = bpath.read_text(encoding="utf-8", errors="replace")
        return ev

    def body(self, ev_id: str) -> str:
        ev = self.get(ev_id)
        return ev.body if ev else ""

    def ids(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.stem for p in self.root.glob("ev_*.json"))

    def count(self) -> int:
        return len(self.ids())

    def render(self, ev_id: str) -> str:
        """Human/agent-readable dump, with the body elided to a preview."""
        ev = self.get(ev_id)
        if ev is None:
            return f"(no evidence {ev_id})"
        head = json_dumps({k: v for k, v in ev.as_dict().items() if k != "body"})
        preview = (ev.body or "")[:2000]
        return f"{head}\n--- body preview ({ev.body_chars} chars) ---\n{preview}"
