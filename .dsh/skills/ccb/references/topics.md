# Topic mining — how `ccb topics` works, and why

The design rule that shapes everything: **the tool never writes prose.** It returns
evidence, structure, counts and a rating with its reasoning. The agent writes the
topic. A claim with no anchor is not a claim the tool will make.

```bash
$CCB topics survey "<direction>"        # 1
$CCB topics gaps <survey_id>            # 2
$CCB topics candidates <survey_id>      # 3
$CCB topics draft <candidate_id>        # 4   <- commits to exactly one
#    ... compose the sections from their anchors ...
$CCB topics rate <topic_id> [--venue X] # 5
$CCB topics save <topic_id>             # 6
$CCB topics list                        # history
$CCB topics venues [query] [--verify]   # the CCF catalogue
$CCB topics operators                   # the novelty operator catalogue
```

---

## 1. `survey` — what the corpus actually holds

Returns counts and lists, not a summary: works, years, venues with their CCF rank,
top authors, ranked terms, and the compact record of every work in scope.

**Corpus top-up.** If the direction has fewer than `--min-works` (default 20) works or
fewer than `--min-fulltext` (default 5) with stored full text, the survey adds works
from the channels and fetches text for those that can supply it, reporting
`expansion.added` / `expansion.indexed` and any per-channel errors. This reuses
`ccb find` / `ccb get` rather than a second acquisition path.

Under `--offline` it does not try, and says the corpus was left as it is. `sufficient:
false` means exactly what it says — **do not mine anyway.** A gap claim the corpus
cannot support is worse than no topic.

`survey_id` is a hash of (query, window, the sorted work ids), so the same direction
over the same corpus gives the same id and the same numbers. Surveys are stored at
`<library>/topics/surveys/<survey_id>.json`.

**Finding the works.** The full-text index is the first choice, but it matches
AND-ish: a query like "graph neural networks for molecules" can miss papers that any
single term would find. When the index comes back thin the survey widens to a keyword
scan over title and abstract, and `found_via` says which happened.

---

## 2. `gaps` — the evidence a topic stands on

Three kinds, all of them things the corpus says rather than things the tool infers:

### Declared gaps

Sentences where an author states a limitation, an assumption, a cost, an absence, or
future work. Each hit carries `work_id`, `page` (or `null` for an abstract),
`sentence`, the matched `marker`, and a `kind`.

This is the strongest signal available. An author writing *"future work will explore
X"* has already named a topic, and the sentence is quotable evidence for it.

### Six gap kinds

Every declared gap is labelled, because the kinds support quite different topics:

| kind | What the sentence says | Operators it feeds |
|---|---|---|
| `future_work` | the author names the next step | transfer, new-setting, revalidate |
| `absence` | nobody has studied this | fill-absence, transfer, benchmark, integrate |
| `limitation` | this holds only in some regime | boundary, paradox |
| `inefficiency` | this is too expensive at scale | scale-up |
| `idealization` | this assumes something unreal | relax-assumption |
| `breadth` | this is too coarse to be useful | benchmark, paradox |

Markers are matched case-insensitively in English and Chinese (`未来工作`,
`未考虑`, `缺乏`, …). A sentence matching several kinds takes the first in the order
above — future work outranks everything, because the author has spoken directly.

### Sparse term pairs

Two concepts the direction uses heavily but rarely together. This is the computable
form of the **A + B recombination** move:

```
expected   = docs(a) * docs(b) / works      # if the two were independent
deficit    = expected - together
```

A pair is reported when `deficit >= 1.0`; pairs that co-occur about as often as
independence predicts are excluded, because there is no opening there. Counts are
document frequency, not raw occurrences, so one long paper cannot manufacture a theme.

`gap_kinds` tallies what was found. `usable: false` (with exit 3) means there is
nothing to mine — say so rather than lowering the bar.

---

## 3. `candidates` — (evidence × operator), ranked

Each piece of evidence is read through every operator that accepts its kind. Each
candidate carries its evidence, the operator's difficulty and ceiling, a question
skeleton, a score, the score's four parts, and the stored works that share its terms.

### The score

Four weighted parts, each normalised against the direction's corpus size, each reported
with its value and its reason:

| Part | Weight | Is high when |
|---|---|---|
| `directness` | 0.35 | an author states the gap (1.0) rather than it being inferred (0.5) |
| `support` | 0.25 | many of the direction's works bear on this evidence |
| `ambition` | 0.20 | the operator is rated ambitious (2/5 → 0.0 … 5/5 → 1.0) |
| `novelty` | 0.20 | few stored works share the candidate's terms |

`score_basis` lists all four, so the number can be recomputed by hand:
`score = Σ value × weight`. **A score orders a reading list. It is not a prediction.**

Ties break on operator difficulty, then on an author's sentence over a statistic, then
on the id — so repeated runs give the same order.

### `local_coverage`

The stored works sharing the candidate's terms, as a reading list. The count is the
true number of matches. **Read these before claiming the combination is unstudied** —
if several works already combine the two concepts, the novelty claim does not survive
contact with the corpus.

### One at a time

`candidates` proposes; `draft` commits. Every committed topic retires a
`dedup_key` of the form `<operator_id>::<evidence_key>`, and retired combinations are
filtered out of later runs (`excluded_as_mined`). Without this, mining the same
direction twice yields the same idea in new words.

Use `--include-mined` to see them anyway.

---

## 4. `draft` — the skeleton, with an anchor on every claim

Commits to one candidate and returns the sections a paper of this kind needs. The tool
writes no prose; each section carries `purpose` (what it is for), `write` (the
questions it must answer) and `anchors` (what it may cite).

| # | Section | What it is for |
|---|---|---|
| 1 | Background and problem | why it matters, before any gap is named |
| 2 | Related work and the gap | the four-step derivation: what prior work did → what it could not → your move → expected value |
| 3 | Research questions and hypotheses | falsifiable, with the one-sentence claim test |
| 4 | Contributions | one line each, labelled with the operator's novelty type and difficulty |
| 5 | Technical approach | what is reused, what is new, the single mechanism |
| 6 | Expected experiments and datasets | see below |
| 7 | Expected contributions and anticipated criticism | the three hardest reviewer questions, written now |
| 8 | References | only works the library holds |
| 9 | Evidence appendix | every quotation, with work_id and page |

**Datasets and baselines** are harvested from the corpus by pattern (`on the X dataset`,
`the X benchmark`, `compared with X`, `outperforms X`) and reported with their mention
counts. A name appearing there means neighbouring work mentions it — **not** that it
fits your question. Verify licence, size and availability.

Every anchor is either a `quotation` (with `work_id` + `page` + `sentence`) or a
`statistic` (with the term pair and its counts). Nothing else is representable, which
is what makes the anchor invariant testable.

---

## 5. `rate` — the CCF estimate

An upper bound, a band, a confidence, and **every movement with its reason**. Never a
promise. Five inputs, all recomputable:

1. **Operator ceiling** — the starting upper bound. An application of an existing
   method does not reach a top venue; a new framework can.
2. **Declared or inferred** — an author's own sentence, or a co-occurrence statistic.
   Inferred costs one band.
3. **Corpus support** — below 30% of the direction's works, one band.
4. **Local coverage** — above 60% of the works sharing the terms, one band.
5. **Operator difficulty** — at or below 2/5 (an incremental move), one band.

`--venue X` looks the target up in the catalogue: a known venue's own rank caps the
estimate, and an operator whose ceiling is below the target's band raises an explicit
warning. An unknown venue is reported as `unmatched` — **no rank is interpolated from a
similar name.**

`confidence` is `high` / `medium` / `low` from how many bands were lost. `risks` lists
the same reasons in prose. The disclaimer is part of the output, not decoration.

---

## The CCF catalogue

`ccb topics venues` reads a CSV of the form:

```csv
abbr,aliases,name,kind,field,rank
NeurIPS,NIPS,Conference on Neural Information Processing Systems,conference,Artificial Intelligence,A
```

Two things are deliberate:

- **The bundled file is a curated subset** of the CCF recommended list covering
  mainstream CS venues — not the official document. Set `CCB_CCF_CATALOG` to your own
  CSV to replace it wholesale, and run `ccb topics venues --verify` to check one
  before trusting it. Verification reports duplicates and malformed rows.
- **Unmatched is a real answer.** A venue not in the catalogue resolves to `None` and
  the rating says so. Matching is conservative: an abbreviation must appear as a
  contiguous run of tokens, or a name must match exactly. Substring matching is not
  used, because `ai` is a substring of `artificial`, and a wrong rank is worse than no
  rank.

Matching precedence: exact abbreviation/alias → exact name → abbreviation as a token
run → unambiguous long-name containment, with a check that a string saying
"conference" does not resolve to a journal of the same name.

---

## The novelty operators

Eleven moves, each with the novelty type and difficulty the literature associates with
it. `ccb topics operators` lists them machine-readably.

| id | Move | Type | Difficulty | Ceiling | Consumes |
|---|---|---|---|---|---|
| `recombination` | A + B → C | fusion | 3 | B | sparse pair |
| `transfer` | import a mature method across a boundary | application | 2 | C | absence, future work |
| `new-setting` | mature method, new setting or dataset | application | 2 | C | future work, absence |
| `revalidate` | new technique on a settled question | comparison | 4 | B | future work, absence |
| `relax-assumption` | drop a simplifying assumption | modification | 3 | B | idealization |
| `scale-up` | remove the scaling wall | modification | 3 | B | inefficiency |
| `fill-absence` | do the thing that is said to be undone | modification | 3 | B | absence |
| `boundary` | turn a limitation into a precise condition | theory | 5 | A | limitation |
| `benchmark` | rival families under one protocol | comparison | 4 | B | absence, breadth |
| `integrate` | bridge two theoretical accounts | fusion | 3 | A | sparse pair, absence |
| `paradox` | explain a documented contradiction | theory | 5 | A | limitation, breadth |

Difficulty follows the field's own ordering: a new problem with a new method outranks a
new method for an old problem, which outranks an old method for a new problem.

Operators generate **question skeletons**, not sentences. `recombination` produces
*"the direction uses both {a} and {b} heavily but almost never together
({together} of {total} works, against {expected} expected). What does applying {a} to
the problem that {b} addresses buy, and on which measure?"* — a question to answer, not
prose to paste.

---

## On disk

```
<library>/topics/
  index.json                mined-topic history and the retired de-duplication keys
  surveys/<id>.json         a domain survey
  candidates/<id>.json      a candidate set (self-contained: embeds the survey it used)
  records/<id>.json         a committed topic: operator, evidence, sections, rating
  drafts/<id>.md            the Markdown draft exported by `topics save`
```

Plain JSON and Markdown, for the same reason the rest of the library is: diffable,
greppable, rebuildable. Every write is recorded in the library ledger.

---

## Traps worth knowing

- **A thin corpus is the common failure, not a bug.** Five works cannot establish a
  field-wide gap. Let the survey top the direction up, or accept `sufficient: false`.
- **Abstracts pollute the term layer.** A paper's abstract often mentions methods from
  other clusters, which weakens the sparse-pair signal. Read `local_coverage`.
- **CJK bodies yield no terms.** The term extractor is Latin-script only by design; a
  mostly-Chinese corpus is reported as having a thin term layer rather than mined for
  fragment noise. Metadata, venue ranking and CCF still work.
- **Fuzzy dedup can collapse a synthetic test corpus.** Works whose titles differ only
  by a single character (which the tokenizer drops) are treated as one. Real corpora do
  not look like that; test fixtures must not either.
- **The rating is an estimate.** Present it with its basis and risks, never as a
  prediction of acceptance.
