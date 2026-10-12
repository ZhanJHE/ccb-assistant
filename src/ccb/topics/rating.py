"""The CCF rating estimate — an argued estimate, never a promise.

The question "what could this reach?" deserves an answer, and the honest way to give
one is to state the ceiling the *kind* of contribution supports, then walk it down by
the specific weaknesses of *this* topic, showing every step. So the output is an upper
bound, a band, the basis for each movement, and a confidence — not a number that looks
like a prediction.

The five inputs are all recomputable by hand:

1. **The operator's ceiling.** An application of an existing method does not reach a
   top venue; a new framework can. This is the starting upper bound.
2. **Whether the gap is declared.** An author writing "future work will explore X" is
   direct evidence; a sparse co-occurrence statistic is an inference.
3. **How much of the corpus supports it.** One paper's aside is not a field-wide gap.
4. **How covered the combination already is locally.** If many stored works share the
   candidate's terms, the novelty claim needs reading before it is made.
5. **The target venue**, when one is named: its own catalogue rank, and whether the
   operator is capable of reaching a venue of that band at all.

When the target venue is not in the catalogue the estimate says so and reports only
what it can support. It does not interpolate a rank from a similar name, and it never
reports a band it cannot justify from the inputs above.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..core.util import utc_now
from .ccf import CcfCatalog, default_catalog
from .store import load_json

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..library.store import Library

BANDS: tuple[str, ...] = ("C", "B", "A")

# Thresholds, named so the reasoning can be checked rather than guessed at.
WEAK_SUPPORT_RATIO = 0.30
HEAVILY_COVERED_RATIO = 0.60
LOW_DIFFICULTY = 2

DISCLAIMER = (
    "This is a rule-based estimate from the evidence recorded with the topic, not a "
    "prediction of acceptance. It says what the kind of contribution and the strength "
    "of its evidence can support, and it names every reason it moved down. Treat a "
    "band as a ceiling to argue against, not a result."
)


def _downgrade(rank: str, steps: int) -> str:
    index = BANDS.index(rank) if rank in BANDS else 0
    return BANDS[max(0, index - steps)]


def _band_floor(left: str, right: str) -> str:
    """The lower of two bands."""
    if left not in BANDS:
        return right if right in BANDS else "C"
    if right not in BANDS:
        return left
    return left if BANDS.index(left) <= BANDS.index(right) else right


def rate(
    library: "Library",
    topic: dict[str, Any] | str,
    *,
    target_venue: str = "",
    catalog: CcfCatalog | None = None,
) -> dict[str, Any]:
    """Estimate the CCF band a topic could reach, with its reasoning."""
    catalog = catalog or default_catalog()
    if isinstance(topic, str):
        loaded = load_json(library, "records", topic)
        if loaded is None:
            return {
                "error": "unknown_topic",
                "topic_id": topic,
                "message": (
                    "No stored topic with that id. Run `ccb topics draft <candidate_id>` "
                    "first."
                ),
            }
        topic = loaded

    operator = topic.get("operator") or {}
    context = topic.get("context") or {}
    ceiling = str(operator.get("ccf_ceiling") or "C")
    difficulty = int(operator.get("difficulty") or 3)
    novelty_type = str(operator.get("novelty_type") or "")
    directness = float(context.get("directness") or 0.5)
    support = int(context.get("support") or 0)
    corpus_works = max(int(context.get("corpus_works") or 0), 0)
    coverage_hits = int(context.get("local_coverage_hits") or 0)

    basis: list[dict[str, Any]] = []
    risks: list[str] = []
    steps = 0

    basis.append(
        {
            "rule": "operator_ceiling",
            "value": ceiling,
            "why": (
                f"a '{novelty_type}' contribution using the "
                f"'{operator.get('id', '?')}' operator has a realistic ceiling of "
                f"CCF-{ceiling}"
            ),
        }
    )

    venue_rank = ""
    if target_venue:
        match = catalog.match(target_venue)
        if match is None:
            basis.append(
                {
                    "rule": "target_venue",
                    "value": "unmatched",
                    "why": (
                        f"'{target_venue}' is not in the catalogue loaded from "
                        f"{catalog.source}; no rank is assumed for it"
                    ),
                }
            )
            risks.append(
                f"The target venue '{target_venue}' is not in the CCF catalogue, so the "
                f"target's own band could not be checked. Set CCB_CCF_CATALOG to a "
                f"catalogue that contains it."
            )
        else:
            venue_rank = match.rank
            basis.append(
                {
                    "rule": "target_venue",
                    "value": venue_rank,
                    "why": f"'{target_venue}' resolves to {match.abbr}, CCF-{match.rank}",
                }
            )
            if BANDS.index(ceiling) < BANDS.index(match.rank):
                risks.append(
                    f"The operator's ceiling (CCF-{ceiling}) is below the target venue "
                    f"({match.abbr}, CCF-{match.rank}). As scoped, this contribution is "
                    f"unlikely to reach it; a more fundamental operator would be needed."
                )

    if directness < 1.0:
        steps += 1
        risks.append(
            "The gap is inferred from co-occurrence rather than stated by an author, so "
            "the claim that it is unstudied rests on statistics and must be checked by "
            "reading the works listed under local_coverage."
        )
        basis.append(
            {
                "rule": "evidence_directness",
                "value": "inferred",
                "why": "no author's own sentence supports this; -1 band",
            }
        )
    else:
        basis.append(
            {
                "rule": "evidence_directness",
                "value": "declared",
                "why": "an author states the gap in their own words; no adjustment",
            }
        )

    if corpus_works:
        ratio = support / corpus_works
        if ratio < WEAK_SUPPORT_RATIO:
            steps += 1
            risks.append(
                f"Only {support} of {corpus_works} works in the direction support this "
                f"evidence, which is thin for a field-wide claim."
            )
            basis.append(
                {
                    "rule": "corpus_support",
                    "value": round(ratio, 3),
                    "why": f"{support}/{corpus_works} works; below {WEAK_SUPPORT_RATIO}; "
                           f"-1 band",
                }
            )
        else:
            basis.append(
                {
                    "rule": "corpus_support",
                    "value": round(ratio, 3),
                    "why": f"{support}/{corpus_works} works; no adjustment",
                }
            )

        covered = coverage_hits / corpus_works
        if covered > HEAVILY_COVERED_RATIO:
            steps += 1
            risks.append(
                f"{coverage_hits} of {corpus_works} stored works already share this "
                f"candidate's terms. Read them before claiming the combination is new."
            )
            basis.append(
                {
                    "rule": "local_coverage",
                    "value": round(covered, 3),
                    "why": f"{coverage_hits}/{corpus_works} works share the terms; above "
                           f"{HEAVILY_COVERED_RATIO}; -1 band",
                }
            )
        else:
            basis.append(
                {
                    "rule": "local_coverage",
                    "value": round(covered, 3),
                    "why": f"{coverage_hits}/{corpus_works} works share the terms; no "
                           f"adjustment",
                }
            )
    else:
        risks.append(
            "The topic records no corpus size, so support and coverage could not be "
            "weighed. Re-run `ccb topics draft` so the context is stored."
        )

    if difficulty <= LOW_DIFFICULTY:
        steps += 1
        risks.append(
            f"The operator is rated {difficulty}/5: an incremental move, which limits "
            f"the band regardless of how clean the evidence is."
        )
        basis.append(
            {
                "rule": "operator_difficulty",
                "value": difficulty,
                "why": f"at or below {LOW_DIFFICULTY}/5; -1 band",
            }
        )

    estimated = _downgrade(ceiling, steps)
    if venue_rank:
        estimated = _band_floor(estimated, venue_rank)

    if steps == 0:
        confidence = "high"
    elif steps == 1:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "topic_id": topic.get("topic_id", ""),
        "estimated_ccf": estimated,
        "upper_bound": ceiling,
        "confidence": confidence,
        "steps_down": steps,
        "target_venue": target_venue,
        "target_venue_ccf": venue_rank,
        "basis": basis,
        "risks": risks,
        "disclaimer": DISCLAIMER,
        "computed_at": utc_now(),
    }


def rate_and_store(
    library: "Library",
    topic_id: str,
    *,
    target_venue: str = "",
    catalog: CcfCatalog | None = None,
) -> dict[str, Any]:
    """Estimate, and write the estimate back onto the stored topic."""
    from .store import save_json

    result = rate(library, topic_id, target_venue=target_venue, catalog=catalog)
    if result.get("error"):
        return result
    record = load_json(library, "records", topic_id)
    if record is not None:
        record["rating"] = result
        record["updated_at"] = utc_now()
        save_json(library, "records", topic_id, record)
    return result
