"""Shared low-level helpers: text normalisation, hashing, deterministic serialisation.

Standard library only — this is a deliberate design constraint so the tool can be
dropped into any AI harness without a dependency-resolution step.

This module is **pure**: it computes values from the arguments it is given and touches
no file. The disk half of the old util lives in ``core.files`` (atomic writes, the two
on-disk formats), and ``tests/test_purity.py`` holds this module to that line — a rule
in a docstring is not a boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Iterable

# --------------------------------------------------------------------------- #
# Hashing
# --------------------------------------------------------------------------- #


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def short_hash(*parts: str, length: int = 16) -> str:
    """Stable short hash over the given parts, joined with an unambiguous separator."""
    joined = "\x1f".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:length]


def content_address(data: bytes) -> str:
    """Full content address used for file storage (dedupes identical bytes globally)."""
    return sha256_bytes(data)


# --------------------------------------------------------------------------- #
# Text normalization
# --------------------------------------------------------------------------- #

_LATEX_ACCENTS = {
    r"\'a": "á", r"\'e": "é", r"\'i": "í", r"\'o": "ó", r"\'u": "ú",
    r"\"a": "ä", r"\"o": "ö", r"\"u": "ü", r"\"e": "ë", r"\"i": "ï",
    r"\`a": "à", r"\`e": "è", r"\`i": "ì", r"\`o": "ò", r"\`u": "ù",
    r"\~n": "ñ", r"\c{c}": "ç", r"\aa": "å", r"\o": "ø",
}

_MATH_MACROS = re.compile(
    r"\\(?:textbf|textit|textrm|textsf|texttt|emph|mathrm|mathbf|mathit|text)\s*\{([^{}]*)\}"
)
_LATEX_COMMAND = re.compile(r"\\[a-zA-Z]+\*?(?:\s*\{[^{}]*\})?")
_BRACES = re.compile(r"[{}]")
_DOLLAR = re.compile(r"\$+")
_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")
_PUNCT_EDGE = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)


def strip_latex(text: str) -> str:
    """Best-effort LaTeX-to-plain-text for titles/abstracts coming from arXiv/DBLP.

    Only handles the constructs that actually appear in bibliographic metadata;
    it is not a LaTeX parser and must not be used for document bodies.
    """
    if not text:
        return ""
    out = text
    for src, dst in _LATEX_ACCENTS.items():
        out = out.replace(src, dst)
    # Unwrap formatting macros: \textbf{X} -> X (repeat for nesting)
    for _ in range(3):
        new = _MATH_MACROS.sub(r"\1", out)
        if new == out:
            break
        out = new
    out = out.replace("~", " ")
    out = _LATEX_COMMAND.sub(" ", out)
    out = _BRACES.sub("", out)
    out = _DOLLAR.sub(" ", out)
    # Collapse the whitespace the substitutions above introduce, so that stripping a
    # macro does not leave doubled spaces that would break exact comparisons.
    return _WHITESPACE.sub(" ", out).strip()


def normalize_text(text: str) -> str:
    """Normalize for comparison: NFKC, strip LaTeX, lowercase, collapse whitespace.

    NFKC matters: it folds full-width characters and ligatures so that a title
    scraped from a Chinese-hosted index matches the same title from Crossref.
    """
    if not text:
        return ""
    out = unicodedata.normalize("NFKC", strip_latex(text))
    out = out.casefold()
    out = _NON_WORD.sub(" ", out)
    out = _WHITESPACE.sub(" ", out)
    return out.strip()


def normalize_title(title: str) -> str:
    """Aggressive title normalization for identity and dedup keys."""
    out = normalize_text(title)
    return _PUNCT_EDGE.sub("", out)


def title_tokens(title: str) -> frozenset[str]:
    """Token set for Jaccard similarity (drops very short tokens)."""
    return frozenset(t for t in normalize_title(title).split() if len(t) > 1)


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def normalize_person(name: str) -> str:
    """Reduce a person name to a comparison key.

    Handles the three shapes that actually occur in our sources:
      "Vaswani, Ashish" / "Ashish Vaswani" / "A. Vaswani"
    Returns "lastname|firstinitial" so initials and full names compare equally.

    The comma form must be resolved *before* punctuation is flattened: turning
    "Vaswani, Ashish" into "Vaswani Ashish" would make the family name look like a
    given name and swap the key's two halves.
    """
    if not name:
        return ""
    raw = unicodedata.normalize("NFKC", strip_latex(name)).strip()

    family_hint = ""
    if "," in raw:
        # "Family, Given" (and the "Family, Given Middle" variant).
        family_hint, _, rest = raw.partition(",")
        raw = f"{rest.strip()} {family_hint.strip()}".strip()

    raw = raw.replace(".", " ")
    raw = _NON_WORD.sub(" ", raw)
    parts = [p for p in raw.split() if p]
    if not parts:
        return ""
    honorifics = {"dr", "prof", "professor", "mr", "ms", "mrs", "sir"}
    parts = [p for p in parts if p.casefold() not in honorifics] or parts
    if family_hint:
        family = family_hint.strip().casefold()
        given = parts[0] if parts else ""
        return f"{family}|{given[:1].casefold()}"
    if len(parts) == 1:
        return parts[0].casefold()
    return f"{parts[-1].casefold()}|{parts[0][0].casefold()}"


def first_author_key(authors: list[str] | None) -> str:
    if not authors:
        return ""
    return normalize_person(authors[0])


def normalize_doi(doi: str) -> str:
    """Strip URL prefixes and lowercase; DOIs are case-insensitive per spec.

    OpenAlex returns DOIs as ``https://doi.org/10.x/y``, and arXiv preprints are
    registered under ``10.48550/arXiv.<id>``; both are folded to the bare lowercase
    form so a DOI from one channel compares equal to the same DOI from another.
    """
    if not doi:
        return ""
    out = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
                   "http://dx.doi.org/", "doi:"):
        if out.casefold().startswith(prefix):
            out = out[len(prefix):]
    out = out.strip()
    # A DOI whose suffix carries a URL (observed from OpenAlex: a DOI record whose
    # value is a full "https://doi.org/..." string) is reduced to the identifier part.
    for marker in ("doi.org/", "dx.doi.org/"):
        idx = out.casefold().find(marker)
        if idx > 0:
            out = out[idx + len(marker):]
            break
    return out.strip().casefold()


def arxiv_doi(arxiv_id: str) -> str:
    """The DOI arXiv registers for a preprint (``10.48550/arXiv.<id>``)."""
    aid = normalize_arxiv_id(arxiv_id)
    return f"10.48550/arxiv.{aid}".casefold() if aid else ""


def normalize_acl_id(value: str) -> str:
    """Normalize an ACL Anthology id to its bare form (e.g. ``2024.acl-long.1``)."""
    if not value:
        return ""
    out = value.strip()
    for prefix in ("https://aclanthology.org/", "http://aclanthology.org/",
                   "https://doi.org/10.18653/v1/", "10.18653/v1/", "acl:"):
        if out.casefold().startswith(prefix.casefold()):
            out = out[len(prefix):]
            break
    return out.strip().strip("/").rstrip(".").casefold()


def normalize_pmlr(value: str) -> str:
    """Normalize a PMLR reference to ``<volume>:<page-or-slug>`` when possible."""
    if not value:
        return ""
    out = value.strip()
    for prefix in ("https://proceedings.mlr.press/", "http://proceedings.mlr.press/",
                   "pmlr:"):
        if out.casefold().startswith(prefix.casefold()):
            out = out[len(prefix):]
            break
    out = out.strip().strip("/").removesuffix(".html")
    return out.casefold()


def normalize_arxiv_id(value: str) -> str:
    """Normalize an arXiv ID, dropping any version suffix.

    Handles every shape that actually reaches us: modern (1706.03762v5), legacy
    (hep-th/9901001v2), the arXiv DOI form (10.48550/arXiv.1706.03762), the
    ``arxiv:`` prefix, and full URLs (``http://arxiv.org/abs/1706.03762v5``).

    URL handling must come first: a naive ``split("arxiv.")[-1]`` on
    ``http://arxiv.org/abs/1706.03762`` yields ``org/abs/1706.03762``, which then
    fails to match the same paper found via any other route and forks its identity.
    """
    if not value:
        return ""
    out = value.strip()

    # 1. URLs: take the path segment after /abs/, /pdf/ or /html/.
    m = re.search(r"arxiv\.org/(?:abs|pdf|html|e-print)/([^\s?#]+)", out, re.IGNORECASE)
    if m:
        out = m.group(1)
    else:
        # 2. arXiv DOI form.
        m = re.search(r"10\.48550/arxiv\.([^\s?#]+)", out, re.IGNORECASE)
        if m:
            out = m.group(1)

    # 3. Strip scheme prefixes, a trailing .pdf, and any version suffix.
    out = re.sub(r"^arxiv[:\s]+", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\.pdf$", "", out, flags=re.IGNORECASE)
    out = out.strip().strip("/")
    out = re.sub(r"v\d+$", "", out)
    return out.strip()


# --------------------------------------------------------------------------- #
# JSON (serialisation only — the file writes live in core.files)
# --------------------------------------------------------------------------- #


def json_dumps(obj: Any) -> str:
    """Stable JSON: sorted keys, UTF-8 preserved, no ASCII escaping of CJK."""
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def utc_now() -> str:
    """ISO-8601 UTC with a trailing Z, second precision."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(text: str, maxlen: int = 60) -> str:
    """Filesystem-safe ASCII slug; CJK is hashed out rather than dropped silently."""
    base = normalize_text(text).replace(" ", "-")
    ascii_only = re.sub(r"[^a-z0-9\-]", "", base)
    ascii_only = re.sub(r"-{2,}", "-", ascii_only).strip("-")
    if len(ascii_only) >= 3:
        return ascii_only[:maxlen].strip("-")
    return "x" + short_hash(text, length=10)


def truncate(text: str, limit: int) -> str:
    if text is None:
        return ""
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"
