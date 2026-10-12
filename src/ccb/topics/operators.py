"""The novelty operators — how research ideas are actually made, made computable.

The literature on "finding an innovation point" converges on a small set of moves, and
they are mechanical enough to encode:

* **Recombination (A + B).** Take a framework the field uses and a module idea it uses,
  and propose C = A' + B'. The signal is two concepts that are individually common but
  rarely studied together — exactly what ``terms.sparse_pairs`` measures.
* **Transfer / mismatch.** Carry a mature method across a disciplinary boundary, where
  insiders find the question obvious and outsiders find it strange.
* **Old bottle, new wine** (a mature method on a new dataset or setting) and **new
  bottle, old wine** (a new technique on a classic problem). Reviewers tolerate both,
  because there is solid prior work to stand on and the contribution is incremental
  but real.
* **Relax an assumption.** The author wrote "we assume ..."; the topic is what happens
  when you do not.
* **Scale up.** The author wrote "does not scale"; the topic is making it scale.
* **Fill a stated absence**, **sharpen a boundary condition**, **benchmark rival
  families**, **integrate two theories**, or **chase a paradoxical result**.

Each operator carries the novelty type and the difficulty it implies, which is what
``rating.py`` later turns into an honest CCF ceiling. The operators generate *question
skeletons*, not prose: a topic still has to be written by the agent, from the evidence.

The difficulty scale follows the ordering the field itself uses: a new problem with a
new method outranks a new method for an old problem, which outranks a new problem
solved with an old method.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The five kinds of innovation point, ordered from incremental to fundamental.
NOVELTY_TYPES: tuple[str, ...] = (
    "application",   # an existing method pointed at a new object
    "modification",  # a small, well-motivated change to an existing framework
    "fusion",        # two ideas combined into one that neither alone provides
    "comparison",    # rival families placed under one fair protocol
    "theory",        # a new framework, bound or mechanism
)

# Difficulty, 2 to 5, mirroring the conventional "star" rating of these moves.
_MIN_DIFFICULTY = 2
_MAX_DIFFICULTY = 5


@dataclass(frozen=True)
class Operator:
    """One way of turning evidence into a topic."""

    id: str
    name: str
    novelty_type: str
    difficulty: int
    # Which kinds of evidence this operator can consume. Either a gap kind from
    # `gaps.GAP_KINDS`, or the literal "sparse_pair".
    accepts: tuple[str, ...]
    # A question skeleton with {a} / {b} (sparse pairs) and {subject} / {kind}
    # (declared gaps). Deliberately a question, not a sentence to paste.
    problem: str
    move: str
    rationale: str
    # The highest CCF band this kind of contribution realistically reaches when the
    # evidence is strong. A ceiling, never a promise.
    ccf_ceiling: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "novelty_type": self.novelty_type,
            "difficulty": self.difficulty,
            "accepts": list(self.accepts),
            "problem": self.problem,
            "move": self.move,
            "rationale": self.rationale,
            "ccf_ceiling": self.ccf_ceiling,
        }


OPERATORS: tuple[Operator, ...] = (
    Operator(
        id="recombination",
        name="A + B recombination",
        novelty_type="fusion",
        difficulty=3,
        accepts=("sparse_pair",),
        problem=(
            "The direction uses both {a} and {b} heavily, but almost never together "
            "({together} of {total} works, against {expected} expected). What does "
            "applying {a} to the problem that {b} addresses buy, and on which measure?"
        ),
        move="Put a method from one cluster to work on the problem of another.",
        rationale=(
            "The two concepts are already trusted by the field, so neither needs "
            "justifying; the contribution is the combination, plus the evidence that "
            "the combination was missing."
        ),
        ccf_ceiling="B",
    ),
    Operator(
        id="transfer",
        name="Cross-domain transfer",
        novelty_type="application",
        difficulty=2,
        accepts=("absence", "future_work"),
        problem=(
            "Which mature method from an adjacent area has not yet been applied to the "
            "object of this direction, and what does it reveal that the current "
            "approach cannot?"
        ),
        move="Import a method across a disciplinary boundary.",
        rationale=(
            "A question insiders never asked because it is obvious to them, and "
            "outsiders never asked because the object is unfamiliar to them."
        ),
        ccf_ceiling="C",
    ),
    Operator(
        id="new-setting",
        name="Mature method, new setting",
        novelty_type="application",
        difficulty=2,
        accepts=("future_work", "absence"),
        problem=(
            "The direction's settings are narrow. Which realistic setting has the "
            "current method never been run on, and does the method still hold there?"
        ),
        move="Apply an established method to a new dataset, domain or population.",
        rationale=(
            "Reviewers are tolerant of this move: there is solid prior work beneath it "
            "and the paper supplies genuinely new evidence."
        ),
        ccf_ceiling="C",
    ),
    Operator(
        id="revalidate",
        name="New technique, classic problem",
        novelty_type="comparison",
        difficulty=4,
        accepts=("future_work", "absence"),
        problem=(
            "Which long-standing claim in this direction has never been re-tested with "
            "current methods, and does it survive?"
        ),
        move="Re-open a settled question with a technique that did not exist then.",
        rationale=(
            "A negative or corrective result is publishable, and the prior work gives "
            "the paper an unimpeachable baseline."
        ),
        ccf_ceiling="B",
    ),
    Operator(
        id="relax-assumption",
        name="Relax a simplifying assumption",
        novelty_type="modification",
        difficulty=3,
        accepts=("idealization",),
        problem=(
            "The work assumes {kind}. What breaks, and what has to change in the "
            "method, when that assumption is dropped?"
        ),
        move="Remove or weaken an assumption the current work depends on.",
        rationale=(
            "The assumption is documented by the authors themselves, so the gap needs "
            "no argument; only the remedy does."
        ),
        ccf_ceiling="B",
    ),
    Operator(
        id="scale-up",
        name="Remove the scaling wall",
        novelty_type="modification",
        difficulty=3,
        accepts=("inefficiency",),
        problem=(
            "The direction's methods are reported as too costly at scale. Which "
            "bottleneck dominates, and what restructuring removes it without losing "
            "quality?"
        ),
        move="Attack the cost that current work reports as prohibitive.",
        rationale=(
            "Cost is measurable, so the contribution can be stated as a ratio rather "
            "than an adjective, and the baseline is already agreed."
        ),
        ccf_ceiling="B",
    ),
    Operator(
        id="fill-absence",
        name="Fill a stated absence",
        novelty_type="modification",
        difficulty=3,
        accepts=("absence",),
        problem=(
            "The corpus states that this is unexplored: {kind}. What is the smallest "
            "study that settles whether the absence matters?"
        ),
        move="Do the thing the literature says nobody has done.",
        rationale=(
            "The strongest opening available, and the one most often over-claimed — so "
            "the claim must be scoped to exactly what is absent, not to the whole area."
        ),
        ccf_ceiling="B",
    ),
    Operator(
        id="boundary",
        name="Sharpen a boundary condition",
        novelty_type="theory",
        difficulty=5,
        accepts=("limitation",),
        problem=(
            "The work holds in some regime and fails outside it ({kind}). Where exactly "
            "is the boundary, and what predicts it?"
        ),
        move="Turn an informal limitation into a precise condition.",
        rationale=(
            "A boundary condition is a theoretical contribution that also explains a "
            "known failure, which is why it survives review at a high venue."
        ),
        ccf_ceiling="A",
    ),
    Operator(
        id="benchmark",
        name="Unify rival families under one protocol",
        novelty_type="comparison",
        difficulty=4,
        accepts=("absence", "breadth"),
        problem=(
            "The direction's methods are evaluated under incompatible settings "
            "({kind}). What does a single controlled comparison show about which family "
            "actually wins, and when?"
        ),
        move="Re-evaluate competing approaches under one fair protocol.",
        rationale=(
            "Comparison work is undervalued and therefore under-supplied, and a clean "
            "protocol is reusable, which drives citations."
        ),
        ccf_ceiling="B",
    ),
    Operator(
        id="integrate",
        name="Bridge two theoretical accounts",
        novelty_type="fusion",
        difficulty=3,
        accepts=("sparse_pair", "absence"),
        problem=(
            "Two accounts of this direction coexist without meeting. What single "
            "framework predicts both sets of observations, and what would falsify it?"
        ),
        move="Connect two theories that explain the same phenomenon separately.",
        rationale=(
            "A framework that subsumes two literatures is a genuinely new contribution "
            "even when neither underlying theory is new."
        ),
        ccf_ceiling="A",
    ),
    Operator(
        id="paradox",
        name="Chase a paradoxical result",
        novelty_type="theory",
        difficulty=5,
        accepts=("limitation", "breadth"),
        problem=(
            "Some findings in this direction point in opposite directions ({kind}). "
            "Under what conditions does each hold, and is there one mechanism behind "
            "both?"
        ),
        move="Explain a contradiction the field has been living with.",
        rationale=(
            "Resolving a documented contradiction is the highest-value move available, "
            "and the contradiction itself is the evidence that it is worth doing."
        ),
        ccf_ceiling="A",
    ),
)

_BY_ID = {op.id: op for op in OPERATORS}


def all_operators() -> tuple[Operator, ...]:
    return OPERATORS


def get(operator_id: str) -> Operator | None:
    return _BY_ID.get(operator_id)


def for_evidence(kind: str) -> list[Operator]:
    """Operators that can consume a given kind of evidence, most fundamental first."""
    wanted = kind.strip()
    matched = [op for op in OPERATORS if wanted in op.accepts]
    matched.sort(key=lambda op: (-op.difficulty, op.id))
    return matched


def ids() -> list[str]:
    return [op.id for op in OPERATORS]


def catalog() -> list[dict[str, Any]]:
    return [op.as_dict() for op in OPERATORS]
