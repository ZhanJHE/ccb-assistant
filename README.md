# CCB Assistant（查查呗论文）— search, library, topics: three modules over one shared floor

> **Breaking change in 0.3.0.** The tool was renamed from `lit` to `ccb`: the package, the
> CLI, the MCP entry point, all 16 tool names and all environment variables carry the new
> name, and **no compatibility layer is kept** — update any `lit` invocation, `LIT_*`
> environment variable or MCP registration you still have.

`ccb` answers three questions that most literature tooling answers separately and badly:

1. **How do I get this paper from any of the sources I have access to?** Free APIs,
   keyed APIs, MCP servers, local CLI tools and hand-supplied PDFs all sit behind one
   interface. Which channel was used, and whether it needed a key, is not your problem.
2. **Why am I downloading and parsing this paper again?** Because nothing was kept.
   `ccb` keeps it.
3. **What should I work on next?** The corpus already documents what the field cannot
   do. `ccb topics` mines that, one topic at a time, with the evidence attached.

The second question is why the library exists; the third is why it is worth keeping.
Existing tools cover *finding* papers extremely well — several mature aggregators span
20+ sources — but they all discard the identity map after each query, so the same paper
rediscovered next week is a new record and the same PDF is fetched and parsed again.

## The three modules

```
topics    mine the corpus for one research topic, with its evidence
   │
search    find and obtain a paper from any legal source
   │
library   the durable local corpus: stable ids, dedup, provenance, evidence
   │
core      records, identities, normalisation, PDF extraction
```

| Module | Package | Owns |
|---|---|---|
| **search** | `ccb.search` | the channel registry (http / cli / mcp / manual), rate limiting and credential transparency, the local-first acquisition protocol |
| **library** | `ccb.library` | work records, raw evidence snapshots, the disposable query index, grounded passage retrieval, citation export |
| **topics** | `ccb.topics` | domain survey, gap mining, novelty operators, candidate ranking, the draft skeleton, the CCF estimate |
| **core** | `ccb.core` | the record models, the `work_id` key chain, text normalisation, PDF extraction |

A module may import only what is listed beneath it. `tests/test_modules.py` parses the
real import graph and fails when a boundary is crossed — and the split paid for itself
immediately by removing two genuine cycles: the channel layer no longer reached into
library storage, and the library no longer depended on citation export.

## What the library does differently

```
GET  arXiv 1706.03762, 2.2 MB PDF
  first pass    ~5-7 s   channels queried, PDF downloaded and stored
  second pass     0.2 s  zero network calls — "Answered from the local library"
  same paper via its DOI instead of its arXiv id   0.2 s, same work_id
```

Three things make that work, and each is a response to a gap the existing landscape
leaves open:

- **Stable two-layer identity.** A `work_id` comes from an explicit, auditable key
  chain (DOI → OpenReview → arXiv → venue ids → title+author+year), so CS conference
  papers that have no DOI — OpenReview submissions, PMLR entries — get a stable
  identity instead of a title hash that changes between runs. A *manifestation* layer
  keeps arXiv v2 and the camera-ready as one work with two carriers.
- **Field-level provenance, never overwritten.** A field is a list of claims, each
  naming its source and the raw response it came from. Disagreements between sources
  stay visible instead of being silently resolved.
- **A library that cannot rot.** Records are plain JSON on disk (diffable, greppable,
  committable); the SQLite index is derived and rebuilt automatically whenever it
  drifts. Every mutation goes through one write path, so the record, the index and the
  audit ledger cannot diverge.

## Clone it and use it

No required third-party dependencies — standard library only, so there is no dependency
step to get wrong. **The clone is the workspace**: the code, your papers, the metadata and
the topic drafts all live in this one directory.

```bash
git clone <this repo> && cd ccb-assistant
python ccb.py channels            # works immediately from a checkout, no install step
python ccb.py find "diffusion models for molecule generation" -n 10
python ccb.py get arxiv:1706.03762 --with-pdf
```

That is the whole setup. The first command creates `papers/`.

### Where your data goes

Everything the tool produces while you use it lands in **`papers/`**, inside this clone:

```
papers/
  library.json  library.jsonl   library metadata, and the append-only ledger
  works/                        one JSON record per paper, with field-level provenance
  evidence/                     raw channel responses, so nothing is ever re-fetched
  files/                        the PDFs
  blobs/                        extracted full text
  index.sqlite                  derived query index — deletable, always rebuildable
  topics/                       mined topics: surveys, candidates, records, drafts
```

The location is resolved from **the clone**, not from your working directory, so calling
the tool from some other project still writes here — the papers stay in the directory you
cloned. To keep several corpora apart, use `--library papers-<topic>` or `$CCB_HOME`.

`papers/` is **local data, and is not in version control**: Git tracks code, tests, dev
docs and the skill only. Two consequences worth knowing:

- It is your **only** copy of the corpus. Back it up by copying the directory.
- Because the directory is ignored wholesale, **`git clean -Xdf` deletes the whole corpus.**

Optionally install it, and add PDF text extraction (the tool works without either):

```bash
pip install -e .                  # provides the `ccb` command
pip install -e ".[pdf]"           # pdfplumber + pypdf for full-text extraction
```

Optional API keys **only raise rate limits**; nothing breaks without them:

| Variable | Effect |
|---|---|
| `CCB_MAILTO` | Joins vendor "polite pools" (Unpaywall requires a real address) |
| `OPENALEX_API_KEY`, `OPENALEX_EMAIL` | Higher OpenAlex budget |
| `S2_API_KEY` | Avoids Semantic Scholar 429s |
| `CORE_API_KEY`, `DOAJ_API_KEY`, `NCBI_API_KEY` | Higher limits |
| `CCB_HOME` | Library location (default `<checkout>/papers`) |
| `CCB_REPO` | Checkout root, for when the skill runs from outside the clone |
| `CCB_CHANNELS` | Extra channel declaration files |
| `CCB_CCF_CATALOG` | Replace the bundled CCF venue catalogue with your own CSV |

## Use

The examples write `ccb`; from a bare checkout, use `python ccb.py` — `cd` into the clone
and everything below works without installing anything.

```bash
ccb channels                                     # what is available, and what is missing
ccb find "diffusion models for molecules" -n 10   # local first, then channels
ccb get arxiv:1706.03762 --with-pdf              # acquire once, idempotently (+ extract)
ccb ask "how does scaled dot-product attention work"   # page-anchored passages
ccb open arxiv:1706.03762 --head 20000            # read locally, zero network
ccb show arxiv:1706.03762                         # which source supplied each field
ccb cite arxiv:1706.03762                         # one entry + field provenance
ccb export --format bibtex -o refs.bib            # bibliography
ccb check --all                                   # re-verify: new version, OA, retraction
```

All commands print JSON on stdout; add `--pretty` for humans (either before or after the
subcommand — `ccb --pretty doctor` and `ccb doctor --pretty` are the same), `--offline` to
forbid the network. One deliberate exception: `ccb export --raw` writes the citation text
itself, for redirection. Exit codes: `0` ok, `2` usage, `3` not found, `4` partial,
`5` failed — and `ccb ask` exits `0` when the corpus simply does not cover the question,
reporting `"outcome": "not-covered"` in the payload, because a coverage gap is not a
failure to look.

### Answering questions from the corpus

`ccb ask` is retrieval, not generation. It returns ranked passages with `work_id` and
**page** anchors so a claim can be checked:

```json
{"grounded": true,
 "hits": [{"work_id": "arxiv:1706.03762", "page": 4, "score": 15.3,
           "citation": "[arxiv:1706.03762 p.4] 2017 Attention Is All You Need",
           "text": "Scaled Dot-Product Attention Multi-Head Attention Figure 2: ..."}]}
```

The agent composes the answer and cites the anchors. If `grounded` is `false`, the
honest response is "the corpus does not cover this" — the tool will not pad a gap with
its least-bad passage, and the skill instructs the agent not to answer from memory.

Ranking is BM25 over a pure-standard-library index: no model download, no API key, no
network, and deterministic — the same question yields the same citations.

## Generating a research topic

`ccb topics` mines the library for **one topic at a time**, and returns evidence rather
than prose. Every claim it produces is anchored to a stored work and a page.

```bash
ccb topics survey "graph neural networks for molecular property prediction"   # 1
ccb topics gaps <survey_id>                  # 2  author-stated gaps + sparse term pairs
ccb topics candidates <survey_id>            # 3  ranked (evidence × novelty operator)
ccb topics draft <candidate_id>              # 4  commit to ONE; the section skeleton
#    ... the agent writes each section from the anchors attached to it ...
ccb topics rate <topic_id> [--venue NeurIPS] # 5  CCF estimate: bound, band, basis, risks
ccb topics save <topic_id>                   # 6  commit, export Markdown, retire the key
ccb topics list                              # what has already been mined
ccb topics venues --verify                   # the CCF catalogue
ccb topics operators                         # the eleven novelty operators
```

What each step actually returns:

- **survey** — works, years, venues *with their CCF rank*, ranked terms, and whether the
  direction is thick enough to mine. Below threshold it tops the corpus up from the
  channels and reports what it added; `sufficient: false` (exit 4) means say so and
  stop rather than mining anyway.
- **gaps** — the strongest signal there is: sentences where an author states a
  limitation, an assumption, a cost, an absence or future work, each with `work_id` and
  `page`. Plus **sparse term pairs**: two concepts the direction uses heavily but rarely
  together, with the arithmetic (`together` vs `expected`) shown so it can be checked.
  That is the computable form of the "A + B" recombination move.
- **candidates** — each (evidence × operator) pair scored on four reported parts:
  how directly the evidence states a gap, how much of the corpus supports it, how
  ambitious the operator is, and how covered the combination already is locally. Ties
  break deterministically. **A score orders a reading list; it is not a prediction.**
- **draft** — the sections a paper of this kind needs (background, the four-step gap
  derivation, research questions, contributions, approach, expected experiments and
  datasets, anticipated criticism, references, evidence appendix), with the anchors each
  section may cite. Datasets and baselines are harvested from neighbouring work as
  *observed mentions with counts* — not recommendations.
- **rate** — an upper bound, a band, a confidence, and **every movement with its
  reason**: operator ceiling, declared vs inferred, corpus support, local coverage,
  operator difficulty. Name a target venue and it checks the estimate against that
  venue's own catalogue rank, warning when the operator cannot reach that band.
- **save** — exports the Markdown draft and retires the topic's de-duplication key, so
  the same combination is never proposed again.

**What it will not do:** write the topic for you, invent a citation, or guess a CCF rank
for a venue that is not in the catalogue. The eleven novelty operators are encoded moves
from the literature on finding an innovation point — recombination, cross-domain
transfer, relaxing an assumption, removing a scaling wall, sharpening a boundary
condition, chasing a paradox — each with the difficulty and realistic ceiling attached.

## Three faces, one core

```
CLI (JSON)  ─┐
Agent Skill ─┼─►  search · library · topics   ← the only place behaviour lives
MCP server  ─┘
```

The three faces are **three entry points into the same directory**, not three ways of
distributing the tool: the CLI is what you type, the skill is what an agent reads, and the
MCP server is what a client registers. All three resolve the same library, in the same
clone, through one core — so they cannot disagree about identity, dedup policy, or what
counts as a legal source.

```bash
python ccb-mcp.py                      # MCP over stdio, no SDK, no extra dependency
python ccb-mcp.py --list-tools
```

Sixteen tools. Search and library: `ccb_contract`, `ccb_channels`, `ccb_find`,
`ccb_get`, `ccb_ask`, `ccb_open`, `ccb_cite`, `ccb_export`, `ccb_stats`. Topic
generation: the seven `ccb_topics_*` tools, one per step. `tests/test_mcp.py` asserts
CLI/MCP parity, and `tests/test_topics.py` drives the whole topics sequence through the
MCP face.

## Agent Skill

The tool ships with a skill in the [Agent Skills](https://agentskills.io/specification)
format, so an agent can drive it without you explaining it:

```
.dsh/skills/ccb/
  SKILL.md                  # what it is, the rules, the canonical step order
  ccb.py                    # launcher (finds the checkout; no copy to drift)
  references/
    topics.md               # the operators, the scoring, the CCF estimate
    architecture.md         # the three modules, on-disk layout, why local-first works
    channels.md             # per-source contracts, measured behaviour, known traps
    commands.md             # every flag with examples
```

It is discovered from `<project>/.dsh/skills` and `~/.dsh/skills` (both scan one level
deep), and `SKILL.md` is kept under the 8192-character render budget with the detail in
`references/`. Because the skill sits inside the clone, an agent working **in this
directory** finds it with no setup at all. To use it from other projects too, copy or
symlink `.dsh/skills/ccb` into `~/.dsh/skills/` — a convenience, not a requirement.

`ccb contract` returns the same operating rules as machine-readable JSON — including the
three modules and the canonical topic-generation sequence — so the contract lives in
code rather than in prose that drifts.

## Channels

| Channel | Status | Role |
|---|---|---|
| `openalex` | works keyless | Broadest index; best open-access locator |
| `crossref` | works keyless | Publisher of record |
| `arxiv` | works | Preprints and LaTeX source |
| `europepmc` | works keyless | Biomedical; genuine full text |
| `openreview` | works keyless | CS conference identity **without DOIs** |
| `paper_search` | if installed | Bridges a local 21-source CLI |
| `unpaywall`, `doaj`, `core` | reachable | OA resolution |
| `dblp` | **gated** | CS authority, currently behind an anti-bot challenge — reported, not worked around |
| `semantic_scholar` | 429 keyless | Supplement only |

Adding a source does not require code: declare it in `<library>/channels.yaml` as
`http`, `cli` or `mcp` with dot-path field mappings. See
[references/channels.md](.dsh/skills/ccb/references/channels.md).

Verified working in all four kinds — **http** (OpenAlex, Crossref, arXiv, Europe PMC,
OpenReview, DBLP), **cli** (a local 21-source tool), **mcp** (a stdio MCP server used
as a source) and **manual** (a PDF you already have) — all landing in the same library
with the same identity rules. A channel that is gated or missing a key degrades and
names the reason rather than returning an empty result.

## Deliberate non-features

- **No Sci-Hub, no Anna's Archive, no mirror hunting.** Open access and
  publisher-sanctioned routes only. Several popular tools embed these; this one does
  not, and says so when a PDF is unavailable.
- **No circumvention of anti-bot challenges.** A gated source is reported as gated.
- **No Google Scholar.** Scraping violates its terms and the anti-bot is unsolved; the
  major `scholarly` library has been unmaintained since 2023.
- **No invented metadata.** A missing volume or page range is omitted, never guessed.
- **No invented ranks or topics.** A venue absent from the CCF catalogue is reported as
  unmatched; a topic claim with no anchor is not emitted at all.

## Development

```bash
python -m unittest discover -s tests -v     # 263 tests, no network, no dependencies
python tools/probe_arxiv.py                 # reproduce a channel's live behaviour
python tools/probe_mcp_source.py            # minimal MCP server used as a test fixture
```

The suite covers identity derivation and normalization, claim/provenance semantics,
dedup thresholds, citation rendering, credential redaction, passage chunking and BM25
ranking, extraction-quality scoring, MCP protocol framing and CLI/MCP parity, all four
channel kinds (http / cli / mcp / manual), library integrity — including the self-healing
paths (a deleted index, a corrupted work file, a merge that must keep the absorbed
identifier resolvable, a re-extraction that must invalidate a stale passage index) — the
module dependency DAG, CCF catalogue matching, term extraction, gap mining, operator
selection, candidate scoring and determinism, the draft anchor invariant, and rating
recomputability.

`notes/` records the landscape survey that shaped the design, including which
capabilities were already well covered and which were empty.
