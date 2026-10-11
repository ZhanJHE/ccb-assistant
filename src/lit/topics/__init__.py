"""Module three — mining the corpus for a research topic worth doing.

The rule that shapes everything here: **this module does not write prose.** It reads
the local corpus and returns structured evidence — gap sentences with page anchors, a
ranked list of novelty-operator candidates, a section skeleton whose every claim
carries the work it came from, and a CCF rating with its per-rule basis. The agent
driving the tool composes the actual topic text from those anchors.

That keeps the module deterministic and testable, and it keeps every claim in a
generated topic checkable against a paper the library actually holds.

The five steps, in the order the contract requires::

    survey    what the corpus holds for a direction, topped up if too thin
    gaps      the evidence: declared limitations, future work, sparse term pairs
    candidates  (evidence x novelty operator), ranked, minus what was already mined
    draft     one topic, as a section skeleton with an anchor on every claim
    rate      the CCF estimate: upper bound, band, basis, confidence, risks
"""

from __future__ import annotations

from . import (
    candidates,
    ccf,
    draft,
    gaps,
    operators,
    rating,
    store,
    survey,
    terms,
)
from .ccf import CcfCatalog, Venue, default_catalog

__all__ = [
    "CcfCatalog",
    "Venue",
    "candidates",
    "ccf",
    "default_catalog",
    "draft",
    "gaps",
    "operators",
    "rating",
    "store",
    "survey",
    "terms",
]
