# Commands

Every command prints one JSON document on **stdout**; diagnostics and errors go to
**stderr**. `--pretty` renders for humans. Global flags may appear before the
subcommand: `--library`, `--pretty`, `--offline`, `--verbose`, `--channel`, `--disable-channel`.

Exit codes: `0` ok · `2` usage · `3` not found · `4` partial · `5` failed.

One nuance worth knowing before you branch: `ask` exits `0` when the corpus does not cover
the question, with `"outcome": "not-covered"` and `grounded: false` in the payload. Only
`3` means "that identifier is not in the library".

## Reading a record

Every stored record carries its provenance. A typical `ccb show` payload:

```json
{"work_id": "arxiv:1706.03762", "has_pdf": true, "has_fulltext": true,
 "field_sources": {"title": ["arxiv", "paper_search"], "year": ["arxiv"]},
 "conflicts": ["venue"]}
```

- `work_id` is **stable** — hand it back verbatim in later calls.
- `field_sources` names the channel behind each field; `conflicts` lists fields where
  sources disagree (report the disagreement, never silently pick one).
- `errors` maps a channel name to why it produced nothing — **"Nothing found" and
  "could not look" are different facts.**

## Credentials — what `channels` tells you

`$CCB channels` reports four credential fields, and never a value:

| Field | Meaning |
|---|---|
| `credentials_present` | variables that are set and in use |
| `credentials_missing` | per channel: `var`, `kind` (`required` = the source cannot be used at all, `optional` = it only raises rate limits), `effect`, and a `note` where the answer is not implied by the declaration |
| `credentials_without_channel` | set, but the channel that consumes it is not loaded — a silent misconfiguration |
| `credential_guidance` | how to talk about a missing key: name the variable, ask the user to set it, never move the value through a conversation |

A channel that needs a credential it does not have is **skipped automatically** and named
in `unavailable` with its reason — one missing key never fails the whole fan-out, and
"nothing found" is never reported when the truth is "could not look".

## Setup

```bash
CCB="python /path/to/ccb-assistant/ccb.py"   # the checkout's own entry point
# or: ccb                                   # if pip install -e . was run

$CCB channels                          # what is available, and what key is missing
$CCB --pretty contract                 # the operating rules, for humans
```

The library defaults to `<checkout>/papers` — inside the clone, wherever you call from.
`--library <dir>` or `$CCB_HOME` override it.

`--pretty`, `--library`, `--offline` and `--verbose` are **global** flags and are accepted
either side of the subcommand — `$CCB --pretty doctor` and `$CCB doctor --pretty` are the
same command.

## find — search local first, then channels

```bash
$CCB find "graph neural networks for drug discovery" -n 10
$CCB find "diffusion models" -n 20 -s openalex,crossref --year-from 2022
$CCB find "retrieval augmented generation" --min-local 5   # only go online if <5 local
$CCB find "transformers" --no-ingest --compact             # look without storing
```

Returns `local_hits` and `fetched` (deduplicated into the library as it goes),
`channels_queried`, and an `errors` map. `local_answered: true` means no channel was
contacted.

## get — acquire one paper, idempotently

Any identifier form works and resolves to the same `work_id`:

```bash
$CCB get 10.1145/3292500.3330701 --with-pdf
$CCB get arxiv:1706.03762 --with-pdf
$CCB get arXiv:1706.03762v5                       # version suffix ignored
$CCB get http://arxiv.org/abs/1706.03762          # URLs accepted
$CCB get openreview:abcDEF123
$CCB get PMID:34265844
$CCB get arxiv:1706.03762 --extract               # extract an already-local PDF
$CCB get <work_id>                                # instant if already local
```

`--with-pdf` also extracts and stores the text, so a later `open` works offline with
no further work. `--extract` alone extracts a PDF that is already present but
unextracted. `--refresh` forces a re-query even on a local hit (used when verifying,
not for normal reads). Re-running on a complete record costs nothing.

## open / extract — read locally, never re-download

```bash
$CCB open <work_id>                  # stored full text, zero network calls
$CCB open <work_id> --head 20000     # first N characters
$CCB extract <work_id>               # PDF → text, once; tries pdfplumber then pypdf
$CCB extract <work_id> --engine pypdf
```

`open` fails with exit 3 rather than silently fetching: if you want the network, say
so with `get`. If extraction reports a short result, the PDF is probably image-only —
use the harness's OCR/PDF skill (`liteparse`) rather than assuming the text is empty.

## inspect

```bash
$CCB show <work_id>            # resolved fields + which source supplied each
$CCB show <work_id> --raw      # the stored record verbatim
$CCB search-local "attention" --venue NeurIPS --with-pdf -n 20
$CCB library stats             # counts, size, year range, conflicts, pending merges
$CCB library list -n 50
$CCB library merges            # duplicate candidates awaiting a decision
$CCB evidence -n 10            # raw response snapshots
$CCB evidence --id ev_arxiv_x  # one snapshot, with a body preview
$CCB ledger -n 30              # append-only audit trail
```

`show` is the command to use when a field matters: `claim_conflicts` shows every
disagreeing value and its source instead of hiding the disagreement.

## ask / index — answer from the corpus, with anchors

```bash
$CCB ask "how does scaled dot-product attention work" -n 5
$CCB ask "what ablation did they run" --ids <work_id> -q 3   # restrict to one paper
$CCB index                        # rebuild passage indexes for stored full texts
$CCB index --ids <work_id>
```

`ask` is a **retrieval** command, not a generator. It returns ranked passages, each
carrying `work_id`, `page`, character offsets and a ready-made `citation` string.
Compose the answer yourself from those passages and cite the anchors.

```json
{"grounded": true,
 "corpus": {"passages": 69, "works": 1},
 "hits": [{"work_id": "arxiv:1706.03762", "page": 4, "score": 15.3,
           "citation": "[arxiv:1706.03762 p.4] 2017 Attention Is All You Need",
           "text": "Scaled Dot-Product Attention Multi-Head Attention Figure 2: ..."}]}
```

Rules that make it trustworthy:

- **`grounded: false` means the corpus does not cover the question.** Say that. Never
  answer from memory or from a paper you did not read.
- Ranking is BM25 with deterministic tie-breaking, so the same question yields the same
  citations — which is what makes a citation checkable.
- Works with no stored full text are listed under `skipped`, so "no stored text" is
  never confused with "nothing matched".
- Exit code 3 when nothing is grounded, so a caller can branch without parsing.
- `--max-per-work` (default 2) stops one long paper from filling every slot.

`get --with-pdf` already indexes on extraction; `index` exists for a corpus populated
before the index did, or after replacing a full-text file.

## cite — one citation, with provenance

```bash
$CCB cite arxiv:1706.03762
$CCB cite 10.1145/3292500.3330701 --format ris
$CCB cite <work_id> --format csl --key-style key
```

Returns the rendered entry plus `provenance` (which source asserted each field) and
`unavailable_fields` (which no source provided). Both matter: a field missing from the
entry is a fact about the metadata, not a tool failure — nothing is ever guessed.

## MCP server

```bash
python ccb-mcp.py                         # serve over stdio, using <checkout>/papers
python ccb-mcp.py --list-tools            # inspect the exposed tools
python ccb-mcp.py --library ./other        # or point it at another corpus
```

Sixteen tools. Search and library: `ccb_contract`, `ccb_channels`, `ccb_find`,
`ccb_get`, `ccb_ask`, `ccb_open`, `ccb_cite`, `ccb_export`, `ccb_stats`. Topic
generation: `ccb_topics_survey`, `ccb_topics_gaps`, `ccb_topics_candidates`,
`ccb_topics_draft`, `ccb_topics_rate`, `ccb_topics_save`, `ccb_topics_list`.
Newline-delimited JSON-RPC 2.0 over stdio, no SDK and no extra dependency. Register it
with any MCP client:

```json
{"mcpServers": {"ccb": {"command": "python", "args": ["/path/to/ccb-assistant/ccb-mcp.py"]}}}
```

Because the CLI and the MCP server are both thin adapters over one core, they cannot
disagree: identical identity rules, identical dedup, identical legal policy. A result
obtained over MCP can be reproduced verbatim from a shell.

Tool failures are returned as data (`{"ok": false, "error": "no_fulltext", ...}`)
rather than as opaque protocol errors, so a caller can read the reason and adapt.

## verify — incremental re-verification

```bash
$CCB check --all                    # re-query only the decisive endpoints
$CCB check <id1>,<id2> -n 5
$CCB check-files                    # PDFs on disk vs recorded sha256; finds orphans
```

`check` is three-valued per record: `changed`, `unchanged`, or `unverifiable`. Absence
of a retraction notice is reported as **"not found in the sources checked"** — never as
"not retracted", because a miss is not evidence.

## citations

```bash
$CCB export --format bibtex -o refs.bib
$CCB export --format bibtex --ids <id1>,<id2>
$CCB export --format ris
$CCB export --format csl            # CSL-JSON for citation processors
$CCB export --format text --query "transformer"      # filter by title/abstract
$CCB export --key-style key          # DOI-derived keys instead of author-year
$CCB export --raw > refs.bib          # the citation text itself, for redirection
```

Output is JSON like every other command (`{"format", "entries", "text"}`). `--raw` is the
explicit opt-in to plain citation text on stdout; without it, `> refs.bib` would capture
JSON.

Citation keys are **stable across exports** (derived from identity, not list position),
so `\cite` commands survive re-export. Missing fields are omitted, never invented —
no guessed volume, page range or DOI.

## maintenance

```bash
$CCB doctor                  # consistency report: index freshness, unreadable files
$CCB doctor --repair         # same, rebuilding derived artefacts
$CCB repair                  # force a full rebuild of derived artefacts
$CCB reindex                 # usually unnecessary: commands self-check and rebuild
$CCB merge <keep_id> <drop_id>   # confirm a flagged duplicate
$CCB add-file ./paper.pdf --title "..." --authors "A One;B Two" --year 2024 --extract
```

`doctor`/`repair` never delete or rewrite `works/*.json`; the worst case is a rebuild.

## topics — mine the corpus for a research topic

Topic generation is a sequence, not a single command, because there is judgement in the
middle: the agent must read the gap evidence before choosing, and choose before
drafting. See `references/topics.md` for the method behind each step.

```bash
# 1. Map the direction. Tops the corpus up from channels when it is too thin.
$CCB topics survey "graph neural networks for molecular property prediction"
$CCB topics survey "<direction>" --min-works 30 --min-fulltext 8   # raise the bar
$CCB topics survey "<direction>" --offline                        # never top up
$CCB topics survey "<direction>" --year-from 2021                 # restrict the window

# 2. The evidence: author-stated gaps (with page anchors) and sparse term pairs.
$CCB topics gaps <survey_id>
$CCB topics gaps <survey_id> -n 120 --max-per-work 5

# 3. Ranked (evidence x novelty operator) candidates.
$CCB topics candidates <survey_id>
$CCB topics candidates <survey_id> -n 10 --include-mined   # include what was mined

# 4. Commit to ONE candidate; returns the section skeleton.
$CCB topics draft <candidate_id>

#    ... write each section from the anchors attached to it ...

# 5. The CCF estimate, with its basis and risks.
$CCB topics rate <topic_id>
$CCB topics rate <topic_id> --venue NeurIPS     # check against a target venue

# 6. Commit: export the Markdown draft and retire the de-duplication key.
$CCB topics save <topic_id>

# Supporting views
$CCB topics list                       # what has been mined, and what each consumed
$CCB topics show <topic_id>            # one record, with anchors and references
$CCB topics show <topic_id> --markdown # the rendered draft
$CCB topics venues NeurIPS             # look a venue up in the CCF catalogue
$CCB topics venues --verify            # self-check the loaded catalogue
$CCB topics operators                  # the eleven novelty operators
```

**Exit codes here carry meaning:** `4` from `survey` means the corpus is below the
thresholds (`sufficient: false`) — say so and stop rather than mining anyway. `3` from
`gaps` means there is no usable evidence. `3` from `candidates` means nothing is left
that has not already been mined.

**Environment:** `CCB_CCF_CATALOG` points at your own CCF catalogue CSV, replacing the
bundled subset. `ccb topics venues --verify` reports duplicates and malformed rows
before you trust one.

**What it will not do:** write the topic for you. Every step returns evidence, counts,
structure and reasoning; the prose is yours, and every claim in it must trace to an
anchor the draft supplied.

## Worked example: search → read → cite, end to end

```bash
# 1. Local first — free if you have already looked at this topic.
$CCB find "speculative decoding for LLM inference" -n 8

# 2. Acquire the ones you need (idempotent; only fetches what is missing).
$CCB get openreview:abcDEF123 --with-pdf --extract
$CCB get 10.48550/arXiv.2211.17192 --with-pdf

# 3. Read from disk — no network, and it works offline afterwards.
$CCB open openreview:abcDEF123 --head 40000

# 4. Answer with page-anchored evidence, then quote the anchors.
$CCB ask "what is the acceptance rate of speculative tokens"

# 5. Cite.
$CCB export --format bibtex --query "speculative decoding" -o related-work.bib
```

Second time round, step 1 answers from the corpus, step 2 is an instant local read, and
steps 3–5 never touch the network. That is the entire point of the tool.

## Worked example: one research topic, end to end

With a corpus already populated (12 works on molecular representation learning):

```bash
$CCB topics survey "molecular" --offline --min-works 5 --min-fulltext 0
# → survey_id 7d318936ac63d45a, corpus {works: 12}, sufficient: true,
#   terms: molecular(12), protein(8), transformer(6), interpretability(4)
#   ccf: {A: 12, unmatched: 0}

$CCB topics gaps 7d318936ac63d45a
# → usable: true, gap_kinds {absence: 3, future_work: 3, idealization: 3, limitation: 3}
#   declared_gaps: 12 (each with work_id, page, sentence, marker)
#   sparse_pairs: ['protein','transformer'] together 2 vs expected 4.0

$CCB topics candidates 7d318936ac63d45a -n 5
# → generated: 66, returned: 5, each with score + score_basis + local_coverage

$CCB topics draft 2ec7ebddcbbe5494
# → topic_id 4e77f9a97b32f0bb, 9 sections, 11 references
#   section 6 observed_datasets: QM9(6), MD17(6)
#   section 6 observed_baselines: SchNet(3), DimeNet(3)

$CCB topics rate 4e77f9a97b32f0bb
# → estimated_ccf B, upper_bound A, confidence medium, steps_down 1
#   basis: operator_ceiling A · evidence_directness declared ·
#          corpus_support 0.25 (-1 band) · local_coverage 0.25

$CCB topics save 4e77f9a97b32f0bb
# → committed; draft at <library>/topics/drafts/4e77f9a97b32f0bb.md
#   1 de-duplication key retired
```

The saved Markdown is a checklist skeleton with every claim's anchor inline — quotations
as blockquotes with `[work_id p.N]`, statistics with their counts, references as BibTeX.
The agent fills it in; the tool never invents a sentence for it.
