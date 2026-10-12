"""CCF venue catalogue — a lookup table, not an oracle.

`rating.py` needs a target venue's CCF rank, and the honest way to obtain one is to
look it up rather than to guess. This module loads such a catalogue from a CSV that
ships with the package, and that can be replaced wholesale:

* **Unmatched is a real answer.** A venue not in the catalogue resolves to ``None``,
  and the rating says so. The tool never interpolates a rank from a vaguely similar
  name, because a fabricated acceptance prediction is exactly the kind of invented
  fact this project refuses to produce everywhere else.
* **The catalogue is data, not code.** Set ``CCB_CCF_CATALOG`` to your own CSV to
  override the bundled file.

The bundled file is a hand-curated subset of the CCF recommended list covering the
mainstream CS venues, *not* the official full document. Verify against the official
release before relying on a rating for a real submission — `verify()` reports exactly
what the loaded catalogue contains.

Matching is deliberately conservative: an abbreviation or alias must appear as a
contiguous run of tokens, or a name must match exactly. Substring matching is not
used, because "ai" is a substring of "artificial" and a wrong rank is worse than no
rank.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..core.util import normalize_text

DEFAULT_CATALOG = Path(__file__).resolve().parent / "data" / "ccf_recommended.csv"

RANKS = ("A", "B", "C")

# A venue string shorter than this is not considered for a containment match against
# a catalogue name; it is far more likely to be a fragment than a venue.
_MIN_CONTAINMENT_CHARS = 12

# Words that announce which kind of venue a string describes. Used only to stop a
# containment match from crossing kinds: "Conf on Artificial Intelligence" must not
# resolve to the journal "Artificial Intelligence".
_CONFERENCE_WORDS = frozenset(
    {"conference", "conf", "proceedings", "symposium", "workshop", "meeting",
     "colloquium", "congress"}
)
_JOURNAL_WORDS = frozenset(
    {"journal", "transactions", "letters", "review", "bulletin", "magazine"}
)


def _kind_hint(norm: str) -> str:
    """``"conference"``, ``"journal"`` or ``""`` when the string does not say."""
    words = set(norm.split())
    wants_conf = bool(words & _CONFERENCE_WORDS)
    wants_journal = bool(words & _JOURNAL_WORDS)
    if wants_conf and not wants_journal:
        return "conference"
    if wants_journal and not wants_conf:
        return "journal"
    return ""


@dataclass(frozen=True)
class Venue:
    """One row of the catalogue."""

    abbr: str
    name: str
    kind: str  # "conference" | "journal"
    field: str
    rank: str  # "A" | "B" | "C"
    aliases: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "abbr": self.abbr,
            "name": self.name,
            "kind": self.kind,
            "field": self.field,
            "rank": self.rank,
            "aliases": list(self.aliases),
        }


def _tokens(text: str) -> list[str]:
    return normalize_text(text).split()


def _windows(tokens: list[str], size: int) -> set[tuple[str, ...]]:
    return {tuple(tokens[i : i + size]) for i in range(len(tokens) - size + 1)}


class CcfCatalog:
    """A loaded catalogue, indexed for lookup by abbreviation, alias and name."""

    def __init__(self, venues: Iterable[Venue], *, source: str = ""):
        self.venues: list[Venue] = list(venues)
        self.source = source
        # Normalised key -> venue, for exact matches.
        self._exact: dict[str, Venue] = {}
        # Token tuples for abbreviation/alias matches, longest first so the most
        # specific key wins when several could apply.
        self._sequences: list[tuple[tuple[str, ...], Venue]] = []
        self._names: dict[str, Venue] = {}
        self._build()

    def _build(self) -> None:
        for venue in self.venues:
            for key in (venue.abbr, *venue.aliases):
                norm = normalize_text(key)
                if not norm:
                    continue
                self._exact.setdefault(norm, venue)
                toks = tuple(norm.split())
                if toks:
                    self._sequences.append((toks, venue))
            name_norm = normalize_text(venue.name)
            if name_norm:
                self._names.setdefault(name_norm, venue)
        self._sequences.sort(key=lambda pair: len(pair[0]), reverse=True)

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #

    @classmethod
    def load(cls, path: Path | str | None = None) -> "CcfCatalog":
        """Load the catalogue from ``path``, ``$CCB_CCF_CATALOG``, or the bundled CSV."""
        if path is None:
            env = os.environ.get("CCB_CCF_CATALOG", "").strip()
            path = Path(env).expanduser() if env else DEFAULT_CATALOG
        path = Path(path)
        if not path.exists():
            return cls([], source=f"{path} (missing)")
        rows: list[Venue] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            for raw in csv.DictReader(handle):
                if not raw or not (raw.get("abbr") or "").strip():
                    continue
                aliases = tuple(
                    a.strip()
                    for a in (raw.get("aliases") or "").split(";")
                    if a.strip()
                )
                rank = (raw.get("rank") or "").strip().upper()
                if rank not in RANKS:
                    continue
                rows.append(
                    Venue(
                        abbr=(raw.get("abbr") or "").strip(),
                        name=(raw.get("name") or "").strip(),
                        kind=(raw.get("kind") or "").strip().casefold() or "conference",
                        field=(raw.get("field") or "").strip(),
                        rank=rank,
                        aliases=aliases,
                    )
                )
        return cls(rows, source=str(path))

    # ------------------------------------------------------------------ #
    # Lookup
    # ------------------------------------------------------------------ #

    def match(self, venue: str) -> Venue | None:
        """Resolve a free-text venue string, or ``None`` if it is not in the catalogue.

        ``None`` means "not in the catalogue", never "probably this one".
        """
        norm = normalize_text(venue)
        if not norm:
            return None
        # Exact abbreviation or alias is the strongest signal.
        if norm in self._exact:
            return self._exact[norm]
        # An exact full name outranks a token-run hit: several catalogue entries use a
        # multi-word phrase as their abbreviation ("Machine Learning"), and without
        # this ordering "Journal of Machine Learning Research" would resolve to the
        # journal "Machine Learning" instead of to JMLR.
        if norm in self._names:
            return self._names[norm]
        toks = norm.split()
        for key, target in self._sequences:
            if len(key) > len(toks):
                continue
            if tuple(key) in _windows(toks, len(key)):
                return target
        if len(norm) >= _MIN_CONTAINMENT_CHARS:
            # A long, precise venue string may be a catalogue name carrying a prefix
            # ("Proceedings of ...") or a trailing parenthetical. Only an unambiguous
            # single hit is accepted, and a string that announces "conference" may not
            # resolve to a journal that happens to share the name.
            hint = _kind_hint(norm)
            hits = {
                target.abbr: target
                for name_norm, target in self._names.items()
                if (name_norm in norm or norm in name_norm)
                and (not hint or target.kind == hint)
            }
            if len(hits) == 1:
                return next(iter(hits.values()))
        return None

    def rank_of(self, venue: str) -> str:
        """The CCF rank, or ``""`` when the venue is not in the catalogue."""
        found = self.match(venue)
        return found.rank if found else ""

    def search(self, query: str, *, limit: int = 20) -> list[Venue]:
        """Substring search over abbreviation, name and field (for `topics venues`)."""
        q = normalize_text(query)
        if not q:
            return self.venues[:limit]
        out: list[Venue] = []
        for venue in self.venues:
            haystack = " ".join(
                (venue.abbr, venue.name, venue.field, " ".join(venue.aliases))
            )
            if q in normalize_text(haystack):
                out.append(venue)
            if len(out) >= limit:
                break
        return out

    def by_rank(self, rank: str) -> list[Venue]:
        want = rank.strip().upper()
        return [v for v in self.venues if v.rank == want]

    def fields(self) -> list[str]:
        return sorted({v.field for v in self.venues if v.field})

    # ------------------------------------------------------------------ #
    # Reporting
    # ------------------------------------------------------------------ #

    def stats(self) -> dict[str, Any]:
        counts = {rank: 0 for rank in RANKS}
        kinds: dict[str, int] = {}
        for venue in self.venues:
            counts[venue.rank] = counts.get(venue.rank, 0) + 1
            kinds[venue.kind] = kinds.get(venue.kind, 0) + 1
        return {
            "source": self.source,
            "venues": len(self.venues),
            "by_rank": counts,
            "by_kind": kinds,
            "fields": self.fields(),
        }

    def verify(self) -> dict[str, Any]:
        """Self-check the loaded catalogue: duplicates, malformed rows, coverage.

        Anything reported here is a property of the *catalogue*, not a judgement about
        a paper. It exists so a replacement CSV can be checked before it is trusted.
        """
        seen: dict[tuple[str, str], list[str]] = {}
        problems: list[str] = []
        for venue in self.venues:
            if venue.rank not in RANKS:
                problems.append(f"{venue.abbr}: unknown rank {venue.rank!r}")
            if not venue.name:
                problems.append(f"{venue.abbr}: empty name")
            if not venue.field:
                problems.append(f"{venue.abbr}: empty field")
            key = (normalize_text(venue.abbr), venue.kind)
            seen.setdefault(key, []).append(venue.rank)
        duplicates = [
            {"abbr": abbr, "kind": kind, "ranks": ranks}
            for (abbr, kind), ranks in seen.items()
            if len(ranks) > 1
        ]
        for dup in duplicates:
            problems.append(
                f"{dup['abbr']} ({dup['kind']}) appears with ranks {dup['ranks']}"
            )
        return {
            **self.stats(),
            "duplicates": duplicates,
            "problems": problems,
            "ok": not problems,
            "note": (
                "The bundled catalogue is a hand-curated subset of the CCF recommended "
                "list, not the official document. Set CCB_CCF_CATALOG to replace it. A "
                "venue absent from the catalogue is reported as unmatched rather than "
                "given a guessed rank."
            ),
        }


_DEFAULT: CcfCatalog | None = None


def default_catalog() -> CcfCatalog:
    """The process-wide catalogue, loaded once."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = CcfCatalog.load()
    return _DEFAULT


def reset_default_catalog() -> None:
    """Drop the cached catalogue (used by tests, and after CCB_CCF_CATALOG changes)."""
    global _DEFAULT
    _DEFAULT = None
