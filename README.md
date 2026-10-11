# lit — one entry point for every paper channel, plus a durable local library

`lit` answers two questions that most literature tooling answers separately and badly:

1. **How do I get this paper from any of the sources I have access to?** Free APIs,
   keyed APIs, MCP servers, local CLI tools and hand-supplied PDFs all sit behind one
   interface. Which channel was used, and whether it needed a key, is not your problem.
2. **Why am I downloading and parsing this paper again?** Because nothing was kept.
   `lit` keeps it.

The second question is the point. Existing tools cover *finding* papers extremely well
— several mature aggregators span 20+ sources — but they all discard the identity map
after each query, so the same paper rediscovered next week is a new record and the same
PDF is fetched and parsed again.

## What it does differently

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

## Install

No required third-party dependencies — standard library only, so there is no
dependency step to get wrong.

```bash
git clone <this repo> && cd ccb_assistant
python lit.py channels            # works immediately from a checkout
```

Optionally install it, and add PDF text extraction:

```bash
pip install -e .                  # provides the `lit` command
pip install -e ".[pdf]"           # pdfplumber + pypdf for full-text extraction
```

Optional API keys **only raise rate limits**; nothing breaks without them:

| Variable | Effect |
|---|---|
| `LIT_MAILTO` | Joins vendor "polite pools" (Unpaywall requires a real address) |
| `OPENALEX_API_KEY`, `OPENALEX_EMAIL` | Higher OpenAlex budget |
| `S2_API_KEY` | Avoids Semantic Scholar 429s |
| `CORE_API_KEY`, `DOAJ_API_KEY`, `NCBI_API_KEY` | Higher limits |
| `LIT_HOME` | Library location (default `./.lit`) |
| `LIT_REPO` | Checkout root, for the Agent Skill launcher |
| `LIT_CHANNELS` | Extra channel declaration files |

## Use

```bash
lit channels                                     # what is available, and what is missing
lit find "diffusion models for molecules" -n 10   # local first, then channels
lit get arxiv:1706.03762 --with-pdf              # acquire once, idempotently (+ extract)
lit ask "how does scaled dot-product attention work"   # page-anchored passages
lit open arxiv:1706.03762 --head 20000            # read locally, zero network
lit show arxiv:1706.03762                         # which source supplied each field
lit cite arxiv:1706.03762                         # one entry + field provenance
lit export --format bibtex -o refs.bib            # bibliography
lit check --all                                   # re-verify: new version, OA, retraction
```

All commands print JSON on stdout; add `--pretty` for humans, `--offline` to forbid the
network. Exit codes: `0` ok, `2` usage, `3` not found, `4` partial, `5` failed.

### Answering questions from the corpus

`lit ask` is retrieval, not generation. It returns ranked passages with `work_id` and
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

## Three faces, one core

```
CLI (JSON)  ─┐
Agent Skill ─┼─►  Library + Resolver   ← the only place behaviour lives
MCP server  ─┘
```

```bash
lit-mcp.py --library ./papers        # MCP over stdio, no SDK, no extra dependency
lit-mcp.py --list-tools
```

Nine tools (`lit_contract`, `lit_channels`, `lit_find`, `lit_get`, `lit_ask`,
`lit_open`, `lit_cite`, `lit_export`, `lit_stats`). Because each face is a thin adapter,
they cannot disagree about identity, dedup policy, or what counts as a legal source —
and `tests/test_mcp.py` asserts that the same call through MCP and through the CLI
produces the same answer.


## Agent Skill

The tool ships as a skill that works with the [Agent Skills](https://agentskills.io/specification)
format, so an agent can drive it without you explaining it:

```
.dsh/skills/lit/
  SKILL.md                  # what it is, the rules, the canonical step order
  lit.py                    # launcher (finds the checkout; no copy to drift)
  references/
    architecture.md         # layers, on-disk layout, why local-first works
    channels.md             # per-source contracts, measured behaviour, known traps
    commands.md             # every flag with examples
```

It is discovered from `<project>/.dsh/skills` and `~/.dsh/skills` (both scan one level
deep), and `SKILL.md` is kept under the 8192-character render budget with the detail in
`references/`. To use it from any project, copy or symlink `.dsh/skills/lit` into
`~/.dsh/skills/`.

`lit contract` returns the same operating rules as machine-readable JSON, so the
contract lives in code rather than in prose that drifts.

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
[references/channels.md](.dsh/skills/lit/references/channels.md).

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

## Development

```bash
python -m unittest discover -s tests -v     # 142 tests, no network, no dependencies
python tools/probe_arxiv.py                 # reproduce a channel's live behaviour
python tools/probe_mcp_source.py            # minimal MCP server used as a test fixture
```

The suite covers identity derivation and normalization, claim/provenance semantics,
dedup thresholds, citation rendering, credential redaction, passage chunking and BM25
ranking, extraction-quality scoring, MCP protocol framing and CLI/MCP parity, all four
channel kinds (http / cli / mcp / manual), and library integrity — including the
self-healing paths (a deleted index, a corrupted work file, a merge that must keep the
absorbed identifier resolvable, a re-extraction that must invalidate a stale passage
index).

`notes/` records the landscape survey that shaped the design, including which
capabilities were already well covered and which were empty.
