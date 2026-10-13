"""Passage-level retrieval over the stored corpus, for grounded citation.

This exists to close the loop that the rest of the tool opens. Having a paper's full
text on disk is not the same as being able to *answer a question from it and point at
where the answer came from*. Without that, an agent either re-reads whole PDFs into
context or, worse, answers from memory.

So this module does the bounded, deterministic half of retrieval-augmented answering:

* **chunk** the stored full text into passages, remembering the page each came from;
* **index** them with BM25 (Okapi) — pure standard library, no model download, no
  network, no API key, and identical output for identical input;
* **retrieve** the top passages for a query and return them with a precise citation
  (`work_id`, page, character offsets, and the passage text).

What it deliberately does **not** do is generate prose. Summarising is the calling
agent's job; supplying verifiable evidence with page-accurate anchors is this tool's
job. Keeping that boundary is what makes a citation checkable — and it is why the
ranking has to be reproducible rather than plausible.

Page numbers come from the extraction step, which splits on form feeds that the PDF
text engines emit, so a citation is anchored to the artefact rather than to a
re-chunking of it.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

# Chunking defaults. Passages are sized for retrieval rather than for reading: about a
# paragraph. Overlap exists so a sentence spanning a boundary is still retrievable
# whole from one of the two passages that contain it.
DEFAULT_PASSAGE_CHARS = 1200
DEFAULT_OVERLAP_CHARS = 200
MIN_PASSAGE_CHARS = 80

# BM25 parameters. `K1` controls term-frequency saturation and `B` length
# normalisation; these are the standard defaults and behave well on prose.
BM25_K1 = 1.5
BM25_B = 0.75

# Function words are dropped because they carry no retrieval signal and would
# otherwise let a long passage accumulate score from "the" and "of".
_STOPWORDS = frozenset(
    """a an the and or but if then than that this these those of in on at to for from by
    with without within into over under between across about as is are was were be been
    being do does did doing have has had having it its it's we our you your they their
    he she his her them us i not no nor so such can could may might must shall should
    will would there here what which who whom when where why how all any both each few
    more most other some only own same too very s t just also""".split()
)

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]*|\d+(?:\.\d+)?|[\u4e00-\u9fff]+")

# Words ending in these are left alone: stripping the final "s" would mangle common
# technical vocabulary ("bias" -> "bia", "analysis" -> "analysi"), and a mangled term
# is worse than an unstripped plural because it silently never matches.
_S_PROTECTED = ("ss", "us", "is", "as", "os", "ics")


def tokenize(text: str, *, keep_stopwords: bool = False) -> list[str]:
    """Tokenize for retrieval: lowercase words, numbers, and CJK runs.

    CJK has no spaces, so a run of Han characters is emitted as one token *and* as
    character bigrams. That keeps a Chinese passage findable by a Chinese query
    without a segmenter, while leaving Latin text on the normal word path.
    """
    out: list[str] = []
    for raw in _TOKEN_RE.findall(text or ""):
        token = raw.casefold()
        if token and token[0].isascii() and token[0].isalpha():
            if not keep_stopwords and token in _STOPWORDS:
                continue
            out.append(_stem(token))
        elif token and token[0].isdigit():
            out.append(token)
        else:
            # CJK run: the whole run plus overlapping bigrams.
            if len(token) > 1:
                out.extend(token[i : i + 2] for i in range(len(token) - 1))
            out.append(token)
    return out


def _stem(token: str) -> str:
    """Fold plural/gerund/past suffixes, protecting technical vocabulary.

    Deliberately conservative: an unstripped plural still matches its singular through
    the query's own stemming, whereas an over-stripped term ("bias" -> "bia") matches
    nothing at all and fails silently.
    """
    if len(token) <= 3:
        return token
    if token.endswith(_S_PROTECTED):
        # "bias", "analysis", "class", "physics" keep their final s.
        if token.endswith("ics"):
            return token
        if token.endswith(("ss", "us", "is", "as", "os")):
            return token
    # "ies" -> "y" only when a consonant precedes, so "ties" -> "ty" is avoided by the
    # length guard below and "series" is protected by the length check.
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("sses"):
        return token[:-2]
    if token.endswith("ing") and len(token) > 5:
        return _undouble(token[:-3])
    if token.endswith("ed") and len(token) > 4:
        return _undouble(token[:-2])
    if token.endswith("es") and len(token) > 4:
        return token[:-1]
    if token.endswith("s"):
        return token[:-1]
    return token


def _undouble(stem: str) -> str:
    """Undo consonant doubling left by suffix removal ("running" -> "runn" -> "run")."""
    if len(stem) > 3 and stem[-1] == stem[-2] and stem[-1] not in "lsz":
        return stem[:-1]
    return stem


def split_pages(text: str) -> list[tuple[int, str]]:
    """Split extracted text into (page_number, page_text).

    PDF text engines separate pages with a form feed. When no form feed is present
    (some extractors drop it) the whole document is page 1 — reported honestly rather
    than guessed, so a citation never claims a page it cannot support.
    """
    if not text:
        return []
    if "\f" not in text:
        return [(1, text)]
    pages = text.split("\f")
    # A trailing form feed produces a final empty page; drop only genuinely empty ones.
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    return [(i, p) for i, p in enumerate(pages, start=1)]


@dataclass
class Passage:
    """A retrievable unit of text with its anchor into the artefact."""

    passage_id: str
    work_id: str
    page: int
    start: int  # character offset within the page
    end: int
    text: str
    token_count: int = 0
    section: str = ""  # chapter heading this passage sits under; "" when undetected

    def as_dict(self, *, with_text: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {
            "passage_id": self.passage_id,
            "work_id": self.work_id,
            "page": self.page,
            "start": self.start,
            "end": self.end,
            "chars": len(self.text),
        }
        if self.section:
            out["section"] = self.section
        if with_text:
            out["text"] = self.text
        return out

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Passage":
        p = Passage(
            passage_id=d.get("passage_id", ""),
            work_id=d.get("work_id", ""),
            page=int(d.get("page", 1) or 1),
            start=int(d.get("start", 0) or 0),
            end=int(d.get("end", 0) or 0),
            text=d.get("text", "") or "",
        )
        p.token_count = int(d.get("token_count", 0) or 0)
        p.section = str(d.get("section", "") or "")
        return p


def chunk_text(
    text: str,
    *,
    work_id: str,
    passage_chars: int = DEFAULT_PASSAGE_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[Passage]:
    """Split stored full text into overlapping passages, page-aware.

    Boundary handling matters: chunks are cut at a sentence or line boundary close to
    the target size where one exists, because a passage that begins mid-sentence reads
    as a broken citation and scores oddly on the first term.
    """
    passages: list[Passage] = []
    counter = 0
    from ..core.sections import detect_sections

    current_section = ""
    for page_no, page_text in split_pages(text):
        stripped = page_text.strip()
        if not stripped:
            continue
        # Work in offsets of the stripped page so `start` is meaningful within the page.
        base = page_text.find(stripped)
        headings = detect_sections(page_text)
        head_at = 0
        pos = 0
        length = len(stripped)
        while pos < length:
            end = min(pos + passage_chars, length)
            if end < length:
                window = stripped[pos:end]
                cut = _last_boundary(window)
                if cut > MIN_PASSAGE_CHARS:
                    end = pos + cut
            chunk = stripped[pos:end].strip()
            is_final = end >= length
            # A chunk sits under the last heading at or before its *end* — a heading in
            # the middle of a chunk names the new chapter, whose content dominates the
            # chunk's tail. A page with no heading inherits the previous page's section:
            # sections run across page breaks the same way they do for a reader.
            while head_at < len(headings) and headings[head_at][0] <= base + end:
                current_section = headings[head_at][1]
                head_at += 1
            # The minimum-length guard suppresses *intermediate* fragments created by
            # boundary snapping, but never the last chunk of a page: a short closing
            # paragraph (a conclusion, an abstract's final sentence, a caption's tail) is
            # real content, and dropping it silently made it unsearchable. That bug is
            # exactly the "answer exists but cannot be found" failure this tool is
            # supposed to prevent.
            if chunk and (is_final or len(chunk) >= MIN_PASSAGE_CHARS):
                counter += 1
                passages.append(
                    Passage(
                        passage_id=f"p{counter:04d}",
                        work_id=work_id,
                        page=page_no,
                        start=base + pos,
                        end=base + end,
                        text=chunk,
                        section=current_section,
                    )
                )
            if is_final:
                break
            # Step forward, keeping the overlap so a sentence across the seam is whole
            # in one of the two passages.
            pos = max(pos + 1, end - overlap_chars)
    for p in passages:
        p.token_count = len(tokenize(p.text))
    return passages


def _last_boundary(window: str) -> int:
    """Offset just past the last sentence/line break in `window`, else its length."""
    best = 0
    for match in re.finditer(r"[.!?][\"')\]]?\s|\n\n|\n", window):
        best = match.end()
    return best if best else len(window)


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #


@dataclass
class Hit:
    """One retrieved passage with its score and citation anchor."""

    passage: Passage
    score: float
    matched_terms: list[str] = field(default_factory=list)
    title: str = ""
    work_year: int | None = None

    @property
    def citation(self) -> str:
        """A short human/agent-readable anchor for this passage."""
        year = f"{self.work_year} " if self.work_year else ""
        return f"[{self.passage.work_id} p.{self.passage.page}] {year}{self.title}".strip()

    def as_dict(self, *, with_text: bool = True) -> dict[str, Any]:
        out = self.passage.as_dict(with_text=with_text)
        out.update(
            {
                "score": round(self.score, 4),
                "matched_terms": self.matched_terms,
                "title": self.title,
                "work_year": self.work_year,
                "citation": self.citation,
            }
        )
        return out


class PassageIndex:
    """In-memory BM25 index over the passages of one or more works.

    Built on demand from the stored passages rather than persisted as a second source
    of truth: the corpus is small enough that construction is cheap, and keeping the
    index derived means it can never disagree with the text it describes.
    """

    def __init__(self, passages: Iterable[Passage]):
        self.passages: list[Passage] = [p for p in passages if p.text]
        self._postings: dict[str, list[tuple[int, int]]] = {}
        self._lengths: list[int] = []
        self._meta: dict[str, tuple[str, int | None]] = {}
        self._build()

    def _build(self) -> None:
        for idx, p in enumerate(self.passages):
            tokens = tokenize(p.text)
            counts = Counter(tokens)
            self._lengths.append(max(1, len(tokens)))
            for term, tf in counts.items():
                self._postings.setdefault(term, []).append((idx, tf))
        self._n = len(self.passages)
        self._avg_len = (sum(self._lengths) / self._n) if self._n else 1.0

    def set_metadata(self, work_id: str, *, title: str, year: int | None) -> None:
        self._meta[work_id] = (title, year)

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        work_ids: Iterable[str] | None = None,
        min_score: float = 0.0,
        max_per_work: int = 0,
    ) -> list[Hit]:
        """Rank passages for a query.

        `max_per_work` is a diversity guard: without it a single long paper can fill
        the whole result set, which is exactly the wrong behaviour when the agent is
        trying to compare sources.
        """
        terms = tokenize(query)
        if not terms or not self.passages:
            return []
        allowed: set[str] | None = set(work_ids) if work_ids else None
        unique_terms = list(dict.fromkeys(terms))
        scores: dict[int, float] = {}
        matched: dict[int, set[str]] = {}
        for term in unique_terms:
            postings = self._postings.get(term)
            if not postings:
                continue
            # Standard BM25 idf with the +0.5 smoothing; clamped at 0 so a term present
            # in more than half the corpus cannot push a passage's score negative.
            df = len(postings)
            idf = max(0.0, math.log(1.0 + (self._n - df + 0.5) / (df + 0.5)))
            for idx, tf in postings:
                p = self.passages[idx]
                if allowed is not None and p.work_id not in allowed:
                    continue
                norm = 1.0 - BM25_B + BM25_B * (self._lengths[idx] / self._avg_len)
                contribution = idf * (tf * (BM25_K1 + 1.0)) / (tf + BM25_K1 * norm)
                scores[idx] = scores.get(idx, 0.0) + contribution
                matched.setdefault(idx, set()).add(term)
        if not scores:
            return []
        # Coverage bonus: a passage matching several distinct query terms is more
        # likely to be *about* the query than one repeating a single term.
        for idx in list(scores):
            coverage = len(matched.get(idx, ())) / len(unique_terms)
            scores[idx] *= 1.0 + 0.35 * coverage

        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        out: list[Hit] = []
        per_work: dict[str, int] = {}
        for idx, score in ranked:
            if score < min_score:
                break
            p = self.passages[idx]
            if max_per_work:
                used = per_work.get(p.work_id, 0)
                if used >= max_per_work:
                    continue
                per_work[p.work_id] = used + 1
            title, year = self._meta.get(p.work_id, ("", None))
            out.append(
                Hit(
                    passage=p,
                    score=score,
                    matched_terms=sorted(matched.get(idx, set())),
                    title=title,
                    work_year=year,
                )
            )
            if len(out) >= limit:
                break
        return out

    def stats(self) -> dict[str, Any]:
        works = {p.work_id for p in self.passages}
        return {
            "passages": len(self.passages),
            "works": len(works),
            "unique_terms": len(self._postings),
            "avg_passage_tokens": round(self._avg_len, 1),
        }


def build_index(
    works: Iterable[Any],
    texts: dict[str, str],
    *,
    passage_chars: int = DEFAULT_PASSAGE_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> PassageIndex:
    """Build an index from works plus their already-loaded full texts."""
    passages: list[Passage] = []
    meta: dict[str, tuple[str, int | None]] = {}
    for w in works:
        text = texts.get(w.work_id)
        if not text:
            continue
        meta[w.work_id] = (w.title(), w.year())
        passages.extend(
            chunk_text(
                text,
                work_id=w.work_id,
                passage_chars=passage_chars,
                overlap_chars=overlap_chars,
            )
        )
    index = PassageIndex(passages)
    for work_id, (title, year) in meta.items():
        index.set_metadata(work_id, title=title, year=year)
    return index


def load_passages(record: dict[str, Any]) -> list[Passage]:
    return [Passage.from_dict(d) for d in (record.get("passages") or [])]
