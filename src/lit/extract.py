"""L3 — full-text extraction, reusing whatever is already installed.

Deliberately does **not** reimplement PDF parsing. It probes for the best available
local engine and reports honestly when none is present, rather than failing
obscurely or shelling out to a service that may not exist:

1. ``pdfplumber`` — best layout fidelity; preferred;
2. ``pypdf`` — pure-Python fallback, adequate for text-layer PDFs;
3. neither — the caller is told to use the harness's own PDF skill (this machine has
   ``liteparse`` and ``markitdown``), which is better than a silently empty extract.

Scanned/image-only PDFs are detected and reported as such, because a "successful"
extraction returning a hundred characters of nothing is worse than an explicit
"this PDF has no text layer".
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from pathlib import Path

# Below this many characters for a whole document, assume there is no text layer.
MIN_PLAUSIBLE_CHARS = 200


@dataclass
class Extraction:
    text: str
    engine: str
    pages: int = 0
    error: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return bool(self.text) and not self.error

    def as_dict(self) -> dict[str, object]:
        return {
            "engine": self.engine,
            "pages": self.pages,
            "chars": len(self.text),
            "ok": self.ok,
            "error": self.error,
            "warnings": list(self.warnings),
        }


def available_engines() -> list[str]:
    found: list[str] = []
    for name in ("pdfplumber", "pypdf", "fitz"):
        try:
            importlib.import_module(name)
            found.append(name)
        except Exception:
            continue
    return found


# --------------------------------------------------------------------------- #
# Text-quality scoring
# --------------------------------------------------------------------------- #
#
# Why this exists: `pdfplumber.extract_text()` on a typical LaTeX-produced paper can
# return text with words jammed together ("Anattentionfunctioncanbedescribed"), because
# the character-gap threshold misreads tight kerning. That text is still "successful"
# extraction by every naive measure — thousands of characters, no exception — but it is
# badly degraded for reading and outright harmful for retrieval, because a search for
# "attention function" will not match "attentionfunction".
#
# Rather than hard-code a fix for one producer's layout, several extraction strategies
# are tried and the best-scoring result wins. The metric rewards word-like output:
# a healthy text layer has a high ratio of single spaces to characters and almost no
# very long unbroken tokens.

_SPACE_RATIO_GOOD = 0.14  # a well-extracted English page is ~15% spaces
_LONG_TOKEN = 22  # characters; beyond this a "word" is almost certainly jammed text
_WORD_RE = re.compile(r"\S+")


@dataclass
class _Quality:
    chars: int
    space_ratio: float
    long_token_ratio: float
    score: float
    jammed: bool


def assess_text_quality(text: str) -> _Quality:
    """Score extracted text for word-separation health (higher is better)."""
    stripped = (text or "").strip()
    n = len(stripped)
    if n < 1:
        return _Quality(0, 0.0, 0.0, 0.0, False)
    spaces = stripped.count(" ")
    words = _WORD_RE.findall(stripped)
    long_tokens = sum(1 for w in words if len(w) > _LONG_TOKEN)
    long_ratio = long_tokens / len(words) if words else 1.0
    space_ratio = spaces / n
    # Reward space density up to the healthy level, punish long unbroken tokens hard.
    space_term = min(space_ratio / _SPACE_RATIO_GOOD, 1.0)
    score = space_term * (1.0 - min(long_ratio * 6.0, 1.0))
    return _Quality(n, space_ratio, long_ratio, score, long_ratio > 0.05)


def _sentence_break_heuristic(text: str) -> str:
    """Insert spaces at boundaries that survive even a badly jammed extraction.

    Only used as a last resort on already-suspect text. Restores the boundaries that
    remain visible when inter-word spaces are lost: a lowercase-to-uppercase transition
    inside a word ("MultiHead" -> "Multi Head"), an acronym boundary, and letter/digit
    changes. Two jammed lowercase words cannot be separated without a dictionary, and
    this function does not pretend otherwise.
    """
    if not text:
        return ""
    # Two passes so that a run like "IsAllYou" gets separated at every internal
    # lower->upper transition ("Is All You"), not just the first one found.
    for _ in range(2):
        text = re.sub(r"([a-z])([A-Z][a-z])", r"\1 \2", text)
        text = re.sub(r"([a-z])([A-Z]{2,})", r"\1 \2", text)
    text = re.sub(r"([a-zA-Z])(\d)", r"\1 \2", text)
    text = re.sub(r"(\d)([a-zA-Z])", r"\1 \2", text)
    return text



def extract_text(
    path: Path | str,
    *,
    engine: str = "",
    max_pages: int = 0,
    best_of: bool = True,
) -> Extraction:
    """Extract text from a PDF by per-page selection across several strategies.

    Two failure modes drove this design, both observed on the same real paper:

    * ``pdfplumber`` returned the **complete** body (35k chars) but with words jammed
      together ("Anattentionfunctioncanbedescribed"), which is useless for phrase
      retrieval;
    * ``pypdf`` returned **cleanly spaced** text but only 9k chars, announcing
      "Rotated text discovered. Output will be incomplete."

    Choosing one engine globally forces a bad trade either way: clean-but-truncated or
    complete-but-unreadable. So each page is scored individually and the best strategy
    *for that page* wins, then the pages are stitched back together. The result is
    complete coverage assembled from whichever engine read each page best, with a
    heuristic space-repair applied only where no strategy managed clean spacing.
    """
    p = Path(path)
    if not p.exists():
        return Extraction("", engine or "none", error=f"file not found: {p}")
    engines = [engine] if engine else available_engines()
    if not engines:
        return Extraction(
            "",
            "none",
            error=(
                "no PDF text extractor is installed (looked for pdfplumber, pypdf, fitz). "
                "Use the harness's PDF skill (e.g. liteparse/markitdown) instead, or "
                "install pdfplumber."
            ),
        )

    errors: list[str] = []
    per_page: dict[int, list[tuple[str, str, _Quality]]] = {}
    total_pages = 0
    for name in engines:
        for variant in _variants_for(name, best_of=best_of):
            label = f"{name}{variant}"
            try:
                out = _run_strategy(name, variant, p, max_pages=max_pages)
            except Exception as exc:
                errors.append(f"{label}: {type(exc).__name__}: {exc}")
                continue
            if not (out.text or "").strip():
                errors.append(f"{label}: produced no text (image-only PDF?)")
                continue
            total_pages = max(total_pages, out.pages)
            for page_no, page_text in enumerate((out.text or "").split("\f"), start=1):
                if not page_text.strip():
                    continue
                per_page.setdefault(page_no, []).append(
                    (label, page_text, assess_text_quality(page_text))
                )

    if not per_page:
        joined = "; ".join(errors)
        return Extraction(
            "",
            engines[0],
            error=f"extraction produced no text — {joined}",
            warnings=("the PDF may be a scan without a text layer; OCR would be required",),
        )

    warnings: list[str] = []
    chosen_labels: dict[str, int] = {}
    repaired_pages = 0
    jammed_pages = 0
    page_texts: list[str] = []
    for page_no in sorted(per_page):
        candidates = per_page[page_no]
        label, text, quality = max(candidates, key=lambda c: c[2].score)
        if quality.jammed:
            fixed = _sentence_break_heuristic(text)
            fixed_q = assess_text_quality(fixed)
            if fixed_q.score > quality.score:
                # Prefer a repaired version only if it actually measures better than
                # every clean candidate on this page.
                best_clean = max(c[2].score for c in candidates)
                text, quality = fixed, fixed_q
                chosen_labels["space-repair"] = chosen_labels.get("space-repair", 0) + 1
                repaired_pages += 1
                if quality.score < best_clean:
                    jammed_pages += 1
            else:
                jammed_pages += 1
        else:
            chosen_labels[label] = chosen_labels.get(label, 0) + 1
        page_texts.append(text)

    combined = "\f".join(page_texts)
    if repaired_pages:
        warnings.append(
            f"{repaired_pages} page(s) had a poorly separated text layer and had spacing "
            "recovered heuristically, so some spaces may be wrong"
        )
    if jammed_pages:
        warnings.append(
            f"{jammed_pages} page(s) still have poor word separation; phrase searches over "
            "those pages may miss matches"
        )
    if len(chosen_labels) > 1:
        warnings.append(
            "per-page extraction strategy: "
            + ", ".join(f"{k} on {v} page(s)" for k, v in sorted(chosen_labels.items()))
        )
    if errors:
        warnings.append("strategy errors: " + "; ".join(errors[:4]))
    stripped = combined.strip()
    if stripped and len(stripped) < MIN_PLAUSIBLE_CHARS:
        warnings.append(
            "extracted text is suspiciously short; the PDF may be image-only or mostly figures"
        )

    engine_label = "+".join(sorted(chosen_labels)) or engines[0]
    return Extraction(combined, engine_label, pages=total_pages or len(page_texts),
                      warnings=tuple(warnings))


def _variants_for(engine: str, *, best_of: bool) -> list[str]:
    """Extraction modes to try for one engine, cheapest/most faithful first."""
    if not best_of:
        return [""]
    if engine == "pdfplumber":
        # Default mode is fast and usually fine; layout mode preserves spacing when the
        # default jams words together, at the cost of inserting column padding.
        return ["", "-layout"]
    if engine == "pypdf":
        return ["", "-layout"]
    if engine == "fitz":
        return ["", "-blocks"]
    return [""]


def _run_strategy(engine: str, variant: str, p: Path, *, max_pages: int) -> Extraction:
    if engine == "pdfplumber":
        return _via_pdfplumber(p, max_pages=max_pages, layout=variant == "-layout")
    if engine == "pypdf":
        return _via_pypdf(p, max_pages=max_pages, layout=variant == "-layout")
    if engine == "fitz":
        return _via_fitz(p, max_pages=max_pages, blocks=variant == "-blocks")
    raise ValueError(f"unknown engine {engine!r}")


def _assess(text: str, pages: int, engine: str) -> Extraction:
    warnings: list[str] = []
    stripped = text.strip()
    if stripped and len(stripped) < MIN_PLAUSIBLE_CHARS:
        warnings.append(
            "extracted text is suspiciously short; the PDF may be image-only or "
            "mostly figures"
        )
    return Extraction(text, engine, pages=pages, warnings=tuple(warnings))


def _via_pdfplumber(p: Path, *, max_pages: int = 0, layout: bool = False) -> Extraction:
    """pdfplumber extraction. `layout=True` preserves spacing at the cost of padding."""
    import pdfplumber  # type: ignore

    chunks: list[str] = []
    total = 0
    with pdfplumber.open(str(p)) as pdf:
        total = len(pdf.pages)
        limit = total if not max_pages else min(total, max_pages)
        for page in pdf.pages[:limit]:
            text = ""
            try:
                if layout:
                    text = page.extract_text(layout=True) or ""
                else:
                    text = page.extract_text() or ""
            except TypeError:
                # Older pdfplumber without the layout kwarg.
                text = page.extract_text() or ""
            except Exception as exc:
                text = f"[[page extraction failed: {type(exc).__name__}: {exc}]]"
            chunks.append(text)
    return Extraction("\f".join(chunks), "pdfplumber", pages=total)


def _via_pypdf(p: Path, *, max_pages: int = 0, layout: bool = False) -> Extraction:
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(str(p))
    total = len(reader.pages)
    limit = total if not max_pages else min(total, max_pages)
    chunks: list[str] = []
    for i in range(limit):
        text = ""
        try:
            page = reader.pages[i]
            if layout:
                try:
                    text = page.extract_text(extraction_mode="layout") or ""
                except TypeError:
                    text = page.extract_text() or ""
            else:
                text = page.extract_text() or ""
        except Exception as exc:
            text = f"[[page extraction failed: {type(exc).__name__}: {exc}]]"
        chunks.append(text)
    return Extraction("\f".join(chunks), "pypdf", pages=total)


def _via_fitz(p: Path, *, max_pages: int = 0, blocks: bool = False) -> Extraction:
    import fitz  # type: ignore  # PyMuPDF

    with fitz.open(str(p)) as doc:  # type: ignore[attr-defined]
        total = doc.page_count
        limit = total if not max_pages else min(total, max_pages)
        chunks: list[str] = []
        for i in range(limit):
            page = doc.load_page(i)
            if blocks:
                # Block mode keeps each block's internal spacing and separates blocks,
                # which usually restores word boundaries that the plain mode loses.
                parts = []
                for block in page.get_text("blocks"):
                    if len(block) >= 5 and isinstance(block[4], str):
                        parts.append(block[4].strip())
                chunks.append("\n\n".join(parts))
            else:
                chunks.append(page.get_text("text"))
    return Extraction("\f".join(chunks), "fitz", pages=total)
