"""Term extraction: what a direction is *about*, deterministically.

Survey and gap mining need two facts about a body of work: which concepts it is built
from, and which pairs of concepts are rarely studied together. That is a term
frequency and co-occurrence problem rather than a semantic-parsing one, and treating
it that way is what keeps the output reproducible — the same corpus yields the same
terms, in the same order, every time.

Terms are unigrams, bigrams and trigrams of *adjacent* content words. Adjacency is
checked against the original token positions, so "attention is all you need" does not
produce the phrase "attention need".

Two deliberate departures from the retrieval tokenizer in ``library.passages``:

* **No stemming beyond a plural fold.** Retrieval wants ``based`` and ``bas`` to
  collide; a term a human has to read and cite does not. Over-stemming would turn the
  reported concept into something that no longer appears in any paper.
* **Latin script only.** The retrieval tokenizer emits CJK character bigrams, which
  make a Chinese passage findable but would flood a term list with fragments. A corpus
  written mostly in CJK is reported as having no usable term layer rather than being
  mined for noise.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#_.\-]*")

# Words that carry no topical information. Kept short on purpose: a domain term that
# happens to be common ("model", "learning") still distinguishes papers from each
# other, so only genuinely empty words are removed.
STOPWORDS = frozenset(
    """
    a about above after again against all also am among an and any are as at be because
    been before being below between both but by can cannot could did do does doing
    during each few for from further had has have having he her here hers him his how
    however i if in into is it its itself just me more most my no nor not of off on once
    one only or other ought our ours out over own same she should so some such than that
    the their theirs them then there these they this those through to too under until up
    very was we were what when where which while who whom why will with would you your
    yours
    paper papers work works study studies approach approaches method methods result
    results show shows shown present presents proposed propose new novel based via using
    use used towards toward within without acm ieee proceedings conference journal
    international national annual ieeeacm
    """.split()
)

# Very short terms are usually noise; "ai" and "ml" are kept because they are real.
_MIN_TERM_CHARS = 3
_SHORT_ALLOWED = frozenset({"ai", "ml", "nlp", "ir", "db", "os", "se", "cv", "rl", "gnn"})


def _singular(word: str) -> str:
    """A conservative plural fold that keeps a term readable."""
    w = word.casefold()
    if len(w) <= 3:
        return w
    if w.endswith(("ss", "us", "is", "ics", "as", "os")):
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("s") and not w.endswith(("ses", "xes", "zes", "ches", "shes")):
        return w[:-1]
    return w


def content_tokens(text: str) -> list[tuple[int, str]]:
    """``(position, term)`` for every content word, positions being the raw order."""
    out: list[tuple[int, str]] = []
    for i, raw in enumerate(_WORD.findall(text or "")):
        # The pattern allows "." and "-" inside a word (c++, f1-score, state-of-the-art)
        # but a sentence-ending period is not part of the term.
        raw = raw.rstrip("._-")
        if not raw:
            continue
        term = _singular(raw)
        if len(term) < _MIN_TERM_CHARS and term not in _SHORT_ALLOWED:
            continue
        if term in STOPWORDS:
            continue
        out.append((i, term))
    return out


def extract_terms(text: str, *, max_n: int = 2) -> set[str]:
    """Every adjacent content-word phrase of up to ``max_n`` words in ``text``."""
    content = content_tokens(text)
    terms: set[str] = set()
    for n in range(1, max_n + 1):
        for start in range(len(content) - n + 1):
            window = content[start : start + n]
            if window[-1][0] - window[0][0] != n - 1:
                continue  # a stopword (or non-word) sits between them
            terms.add(" ".join(term for _, term in window))
    return terms


def document_terms(*parts: str, max_n: int = 2) -> set[str]:
    """Terms for one document, pooled over its title, abstract and so on."""
    pooled = " . ".join(p for p in parts if p)
    return extract_terms(pooled, max_n=max_n)


def term_frequencies(
    docs: Iterable[set[str]],
    *,
    top: int = 40,
    min_docs: int = 2,
    max_n: int = 2,
) -> list[dict[str, Any]]:
    """Rank terms by how many documents use them.

    Ranking is by document frequency, not raw count, so one long paper cannot make a
    term look like a theme. Ties break on the term itself, which keeps the ordering
    stable across runs.
    """
    frequency: Counter[str] = Counter()
    total = 0
    for terms in docs:
        total += 1
        for term in terms:
            words = term.count(" ") + 1
            if words > max_n:
                continue
            frequency[term] += 1
    ranked = [
        {"term": term, "docs": count}
        for term, count in frequency.items()
        if count >= min_docs
    ]
    ranked.sort(key=lambda row: (-row["docs"], row["term"]))
    return ranked[:top]


def cooccurrence(
    doc_terms: list[set[str]],
    pairs: Iterable[tuple[str, str]],
) -> dict[tuple[str, str], int]:
    """How many documents contain both terms of each pair."""
    wanted = set(pairs)
    counts: dict[tuple[str, str], int] = {pair: 0 for pair in wanted}
    for terms in doc_terms:
        for pair in wanted:
            if pair[0] in terms and pair[1] in terms:
                counts[pair] += 1
    return counts


def sparse_pairs(
    doc_terms: list[set[str]],
    ranked: list[dict[str, Any]],
    *,
    min_docs: int = 3,
    limit: int = 30,
    max_pairs: int = 4000,
    min_deficit: float = 1.0,
) -> list[dict[str, Any]]:
    """High-frequency term pairs that almost never appear in the same document.

    This is the computable form of the "A + B" move: two concepts the field uses
    heavily, but rarely together, are exactly what a recombination-style topic is made
    of. Only unigrams take part, so the pairs are readable and the arithmetic is easy
    to check by hand.

    Ranking is by *deficit* — how far below the co-occurrence you would expect if the
    two terms were independent — with ties broken by the smaller count and then the
    term names, so the order is stable.
    """
    singles = [row for row in ranked if " " not in row["term"] and row["docs"] >= min_docs]
    total = max(len(doc_terms), 1)
    candidates: list[tuple[str, str]] = []
    for i, left in enumerate(singles):
        for right in singles[i + 1 :]:
            candidates.append((left["term"], right["term"]))
            if len(candidates) >= max_pairs:
                break
        if len(candidates) >= max_pairs:
            break

    observed = cooccurrence(doc_terms, candidates)
    out: list[dict[str, Any]] = []
    for (a, b), together in observed.items():
        docs_a = next(row["docs"] for row in singles if row["term"] == a)
        docs_b = next(row["docs"] for row in singles if row["term"] == b)
        expected = (docs_a * docs_b) / total
        if expected <= 0:
            continue
        deficit = expected - together
        if deficit < min_deficit:
            # Not actually sparse: the two terms appear together about as often as
            # independence would predict, so there is no recombination opening here.
            continue
        out.append(
            {
                "terms": [a, b],
                "together": together,
                "expected": round(expected, 2),
                "deficit": round(deficit, 2),
                "docs_a": docs_a,
                "docs_b": docs_b,
            }
        )
    out.sort(key=lambda row: (-row["deficit"], row["together"], row["terms"][0], row["terms"][1]))
    return out[:limit]
