"""HTTP transport: rate limiting, retries, credential transparency.

Every byte a channel pulls in goes through here, so four cross-cutting concerns are
solved once instead of in each channel:

* **Politeness.** Per-host token-bucket rate limiting, because arXiv wants 3s
  between requests and several APIs 429 aggressively (Semantic Scholar answered 429
  on the very first keyless call during development).
* **Truthful failure.** A 200 is not success: arXiv returns an Atom feed containing
  a single entry literally titled "Error", Europe PMC puts ``errCode`` in a 200
  body. Callers get the raw bytes plus status and must check the payload.
* **Credential hygiene.** Callers pass parameter *names* whose values come from the
  environment; the value is never returned, logged, or echoed. This is what makes
  paid/keyed channels transparent to the user.
* **Zero dependencies.** ``urllib`` only. No requests, no httpx, so the tool drops
  into any harness without an install step.
"""

from __future__ import annotations

import gzip
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field
from typing import Any

from ..core.util import utc_now

# A descriptive UA gets better behaviour from several scholarly APIs and is basic
# good manners. Override with LIT_MAILTO so vendors can contact a real person.
DEFAULT_UA_TEMPLATE = "lit/0.1 (+https://github.com/local/lit; mailto:{mailto})"
FALLBACK_UA = "lit/0.1 (academic literature client)"

# Credentials are read from the environment only, and only these names are ever
# consulted — an allow-list, so a stray variable can never be forwarded silently.
KNOWN_CREDENTIALS: dict[str, str] = {
    "CORE_API_KEY": "core",
    "DOAJ_API_KEY": "doaj",
    "S2_API_KEY": "semantic_scholar",
    "SEMANTIC_SCHOLAR_API_KEY": "semantic_scholar",
    "NCBI_API_KEY": "pubmed",
    "OPENALEX_API_KEY": "openalex",
    "OPENALEX_EMAIL": "openalex",
    "UNPAYWALL_EMAIL": "unpaywall",
    "PAPER_SEARCH_MCP_UNPAYWALL_EMAIL": "unpaywall",
    "IEEE_API_KEY": "ieee",
    "ACM_API_KEY": "acm",
    "ZENODO_ACCESS_TOKEN": "zenodo",
    "MINERU_TOKEN": "mineru",
}


class CredentialError(RuntimeError):
    """Raised internally when a channel needs a credential that is not configured."""


@dataclass
class Response:
    """A raw HTTP result. `ok` means transport succeeded, not that the data is valid."""

    status: int
    body: str
    content_type: str = ""
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    error: str = ""
    attempts: int = 1
    elapsed_ms: int = 0

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and not self.error

    def json(self) -> Any:
        """Parse JSON, raising a message that names the real problem.

        A number of scholarly endpoints answer errors as HTML or plain text with
        200, so the failure has to be described in terms of the body, not the code.
        """
        text = self.body or ""
        stripped = text.lstrip()
        if not stripped:
            raise ValueError(f"empty response body from {self.url or 'request'}")
        if stripped[0] not in "[{":
            snippet = stripped[:200].replace("\n", " ")
            if "<html" in stripped[:1000].casefold() or "<!doctype" in stripped[:1000].casefold():
                raise ValueError(f"expected JSON, got an HTML page (status {self.status}): {snippet}")
            raise ValueError(f"expected JSON, got {snippet!r} (status {self.status})")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON from {self.url or 'request'}: {exc}") from exc


@dataclass
class _Bucket:
    """Token bucket, one per host."""

    rate: float = 1.0  # requests per second
    capacity: float = 1.0
    tokens: float = 1.0
    updated: float = 0.0

    def take(self) -> float:
        """Return seconds to wait before the next request."""
        now = time.monotonic()
        if self.updated == 0.0:
            self.updated = now
        elapsed = now - self.updated
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return 0.0
        needed = (1.0 - self.tokens) / self.rate if self.rate > 0 else 1.0
        self.tokens = 0.0
        self.updated = now + needed
        return needed


def mailto() -> str:
    """Contact address for polite pools. Never invent one if the user set none."""
    for name in ("LIT_MAILTO", "UNPAYWALL_EMAIL", "OPENALEX_EMAIL", "NCBI_EMAIL"):
        val = os.environ.get(name, "").strip()
        if val and "@" in val:
            return val
    return ""


def user_agent() -> str:
    m = mailto()
    return DEFAULT_UA_TEMPLATE.format(mailto=m) if m else FALLBACK_UA


def credential(name: str) -> str:
    """Read a credential from the environment. The value is never logged."""
    return os.environ.get(name, "").strip()


def credential_available(name: str) -> bool:
    return bool(credential(name))


def credential_provider(name: str) -> str:
    """Which channel a known credential belongs to (for the `channels` report)."""
    return KNOWN_CREDENTIALS.get(name, "")


class Http:
    """Rate-limited, retrying HTTP client used by every channel."""

    def __init__(
        self,
        *,
        default_rps: float = 1.0,
        timeout: float = 30.0,
        max_retries: int = 3,
        host_rates: dict[str, float] | None = None,
        extra_retry_on: tuple[int, ...] = (),
        verbose: bool = False,
    ):
        self.default_rps = default_rps
        self.timeout = timeout
        self.max_retries = max_retries
        self.host_rates = dict(host_rates or {})
        # Some academic APIs answer a transient 404 under load. Retrying those is worth
        # it because the alternative is reporting "unavailable" for a source that is
        # merely busy — but the set is opt-in per host, never global, so a genuine
        # "this DOI does not exist" is not retried three times.
        self.extra_retry_on = tuple(extra_retry_on)
        self.verbose = verbose
        self._buckets: dict[str, _Bucket] = {}
        self.stats: dict[str, int] = {"requests": 0, "retries": 0, "throttled": 0, "errors": 0}

    # ---------------- internals ---------------- #

    def _bucket(self, host: str) -> _Bucket:
        if host not in self._buckets:
            rate = self.host_rates.get(host, self.default_rps)
            self._buckets[host] = _Bucket(rate=rate, capacity=max(1.0, rate), tokens=1.0)
        return self._buckets[host]

    def _wait(self, host: str) -> None:
        delay = self._bucket(host).take()
        if delay > 0:
            self.stats["throttled"] += 1
            time.sleep(min(delay, 10.0))

    @staticmethod
    def _decode_body(raw: bytes, encoding: str) -> str:
        if encoding == "gzip":
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
        elif encoding == "deflate":
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                try:
                    raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                except zlib.error:
                    pass
        return raw.decode("utf-8", errors="replace")

    # ---------------- public API ---------------- #

    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        data: bytes | None = None,
        accept: str = "application/json",
        retry_on: tuple[int, ...] = (429, 500, 502, 503, 504),
    ) -> Response:
        """Perform one request with retries. Never raises on HTTP failure."""
        retry_on = tuple(set(retry_on) | set(self.extra_retry_on))
        query = urllib.parse.urlencode(
            {k: v for k, v in (params or {}).items() if v is not None}, doseq=True
        )
        full = f"{url}?{query}" if query else url
        parsed = urllib.parse.urlparse(full)
        host = parsed.netloc
        hdrs = {"User-Agent": user_agent(), "Accept": accept,
                "Accept-Encoding": "gzip, deflate"}
        if headers:
            hdrs.update(headers)

        started = time.monotonic()
        last = Response(status=0, body="", url=full, error="not attempted")
        for attempt in range(1, self.max_retries + 1):
            self._wait(host)
            self.stats["requests"] += 1
            req = urllib.request.Request(full, data=data, headers=hdrs, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    status = resp.status
                    ctype = resp.headers.get("Content-Type", "")
                    enc = (resp.headers.get("Content-Encoding", "") or "").casefold()
                body = self._decode_body(raw, enc)
                last = Response(
                    status=status,
                    body=body,
                    content_type=ctype,
                    url=full,
                    headers={},
                    attempts=attempt,
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                )
                if status in retry_on and attempt < self.max_retries:
                    self.stats["retries"] += 1
                    time.sleep(self._backoff(attempt))
                    continue
                return last
            except urllib.error.HTTPError as exc:
                try:
                    raw = exc.read()
                    body = self._decode_body(raw, "")
                except Exception:
                    body = ""
                last = Response(
                    status=exc.code,
                    body=body,
                    content_type=exc.headers.get("Content-Type", "") if exc.headers else "",
                    url=full,
                    error=f"HTTP {exc.code}",
                    attempts=attempt,
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                )
                if exc.code in retry_on and attempt < self.max_retries:
                    self.stats["retries"] += 1
                    retry_after = 0.0
                    if exc.headers:
                        try:
                            retry_after = float(exc.headers.get("Retry-After", "0") or 0)
                        except (TypeError, ValueError):
                            retry_after = 0.0
                    time.sleep(retry_after if retry_after > 0 else self._backoff(attempt))
                    continue
                self.stats["errors"] += 1
                return last
            except urllib.error.URLError as exc:
                last = Response(
                    status=0,
                    body="",
                    url=full,
                    error=f"network error: {exc.reason}",
                    attempts=attempt,
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                )
                if attempt < self.max_retries:
                    self.stats["retries"] += 1
                    time.sleep(self._backoff(attempt))
                    continue
                self.stats["errors"] += 1
                return last
            except Exception as exc:  # pragma: no cover - defensive
                self.stats["errors"] += 1
                return Response(status=0, body="", url=full, error=f"{type(exc).__name__}: {exc}")
        return last

    def get_json(self, url: str, **kw: Any) -> tuple[Any | None, Response]:
        """GET and parse JSON, returning (parsed_or_None, response) — never raises."""
        resp = self.request(url, **kw)
        if not resp.ok:
            return None, resp
        try:
            return resp.json(), resp
        except ValueError as exc:
            resp.error = str(exc)
            return None, resp

    def get_text(self, url: str, **kw: Any) -> Response:
        kw.setdefault("accept", "text/plain, */*")
        return self.request(url, **kw)

    def download(self, url: str, *, max_bytes: int = 128 * 1024 * 1024, **kw: Any) -> tuple[bytes, Response]:
        """Fetch binary content without a lossy UTF-8 round-trip."""
        hdrs = {"User-Agent": user_agent(), "Accept": kw.pop("accept", "application/pdf, */*")}
        extra = kw.pop("headers", None)
        if extra:
            hdrs.update(extra)
        params = kw.pop("params", None)
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        full = f"{url}?{query}" if query else url
        host = urllib.parse.urlparse(full).netloc
        last = Response(status=0, body="", url=full, error="not attempted")
        for attempt in range(1, self.max_retries + 1):
            self._wait(host)
            self.stats["requests"] += 1
            req = urllib.request.Request(full, headers=hdrs, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    chunks: list[bytes] = []
                    total = 0
                    while True:
                        chunk = resp.read(256 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > max_bytes:
                            return b"", Response(
                                status=resp.status,
                                body="",
                                url=full,
                                error=f"response exceeds {max_bytes} byte ceiling",
                            )
                        chunks.append(chunk)
                    data = b"".join(chunks)
                    return data, Response(
                        status=resp.status,
                        body="",
                        content_type=resp.headers.get("Content-Type", ""),
                        url=full,
                        attempts=attempt,
                    )
            except urllib.error.HTTPError as exc:
                last = Response(
                    status=exc.code, body="", url=full, error=f"HTTP {exc.code}", attempts=attempt
                )
                if exc.code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    self.stats["retries"] += 1
                    time.sleep(self._backoff(attempt))
                    continue
                self.stats["errors"] += 1
                return b"", last
            except Exception as exc:
                last = Response(status=0, body="", url=full, error=f"{type(exc).__name__}: {exc}")
                if attempt < self.max_retries:
                    self.stats["retries"] += 1
                    time.sleep(self._backoff(attempt))
                    continue
                self.stats["errors"] += 1
                return b"", last
        return b"", last

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(8.0, (2 ** (attempt - 1)) * 0.5) * (0.7 + random.random() * 0.6)

    # ---------------- diagnostics ---------------- #

    def report(self) -> dict[str, Any]:
        return dict(self.stats, hosts=sorted(self._buckets), at=utc_now())


# Signatures of an anti-bot interstitial. These arrive as HTTP 200 with an HTML
# body, which is exactly the "200 is not success" trap this module exists to catch:
# DBLP began fronting its API with an Anubis proof-of-work challenge, so a naive
# client parses HTML as JSON and reports a confusing decode error instead of
# "this source is currently gated".
_CHALLENGE_SIGNATURES = (
    "not a bot",
    "anubis",
    "just a moment",
    "cf-browser-verification",
    "checking your browser",
    "enable javascript and cookies to continue",
    "ddos protection",
)


def is_bot_challenge(body: str, content_type: str = "") -> bool:
    """Detect an anti-bot challenge page served with a success status code."""
    if not body:
        return False
    head = body[:4000].casefold()
    if "<html" not in head and "<!doctype" not in head and "text/html" not in content_type.casefold():
        return False
    return any(sig in head for sig in _CHALLENGE_SIGNATURES)


def challenge_reason(body: str, content_type: str = "") -> str:
    """Actionable explanation for a gated source, so callers can degrade cleanly."""
    head = (body or "")[:4000].casefold()
    if "anubis" in head or "not a bot" in head:
        return (
            "source is gated by an Anubis anti-bot challenge; the channel is "
            "unavailable to non-interactive clients (use another channel)"
        )
    if "cloudflare" in head or "just a moment" in head or "cf-browser" in head:
        return "source is gated by a Cloudflare bot challenge"
    return "source returned an HTML interstitial instead of data"


def looks_like_pdf(data: bytes) -> bool:
    """Verify a payload is a PDF instead of trusting Content-Type.

    Several repositories serve an HTML landing page (or a bot challenge) with a PDF
    content type; storing that as a paper would silently poison the corpus.
    """
    if not data or len(data) < 5:
        return False
    head = data[:1024]
    if head.startswith(b"%PDF-"):
        return True
    # A few publishers prepend junk/BOM before the header.
    idx = head.find(b"%PDF-")
    return 0 <= idx <= 32


def pdf_rejection_reason(data: bytes, resp: Response) -> str:
    """Explain why a downloaded payload is not usable, in actionable terms."""
    if not data:
        return resp.error or f"empty response (status {resp.status})"
    if looks_like_pdf(data):
        return ""
    ctype = (resp.content_type or "").casefold()
    head = data[:700].decode("utf-8", errors="replace").casefold()
    if "cloudflare" in head or "captcha" in head or "just a moment" in head:
        return "blocked by a bot challenge (not a PDF)"
    if "text/html" in ctype or "<html" in head or "<!doctype" in head:
        return "server returned an HTML landing page instead of the PDF"
    if "application/json" in ctype:
        return "server returned JSON (likely an error or metadata endpoint, not a PDF)"
    return f"payload is not a PDF (content-type={ctype or 'unknown'}, {len(data)} bytes)"
