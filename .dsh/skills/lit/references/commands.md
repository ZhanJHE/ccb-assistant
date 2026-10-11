# Commands

Every command prints one JSON document on **stdout**; diagnostics and errors go to
**stderr**. `--pretty` renders for humans. Global flags may appear before the
subcommand: `--library`, `--pretty`, `--offline`, `--verbose`, `--channel`, `--disable-channel`.

Exit codes: `0` ok · `2` usage · `3` not found · `4` partial · `5` failed.

## Setup

```bash
LIT="python /path/to/tools/lit-skill.py"     # from a checkout
# or: lit                                   # if pip install -e . was run

export LIT_HOME=/path/to/papers        # optional; default is ./.lit
$LIT channels                          # what is available, and what key is missing
$LIT contract --pretty                 # the operating rules, for humans
```

## find — search local first, then channels

```bash
$LIT find "graph neural networks for drug discovery" -n 10
$LIT find "diffusion models" -n 20 -s openalex,crossref --year-from 2022
$LIT find "retrieval augmented generation" --min-local 5   # only go online if <5 local
$LIT find "transformers" --no-ingest --compact             # look without storing
```

Returns `local_hits` and `fetched` (deduplicated into the library as it goes),
`channels_queried`, and an `errors` map. `local_answered: true` means no channel was
contacted.

## get — acquire one paper, idempotently

Any identifier form works and resolves to the same `work_id`:

```bash
$LIT get 10.1145/3292500.3330701 --with-pdf
$LIT get arxiv:1706.03762 --with-pdf
$LIT get arXiv:1706.03762v5                       # version suffix ignored
$LIT get http://arxiv.org/abs/1706.03762          # URLs accepted
$LIT get openreview:abcDEF123
$LIT get PMID:34265844
$LIT get arxiv:1706.03762 --extract               # extract an already-local PDF
$LIT get <work_id>                                # instant if already local
```

`--with-pdf` also extracts and stores the text, so a later `open` works offline with
no further work. `--extract` alone extracts a PDF that is already present but
unextracted. `--refresh` forces a re-query even on a local hit (used when verifying,
not for normal reads). Re-running on a complete record costs nothing.

## open / extract — read locally, never re-download

```bash
$LIT open <work_id>                  # stored full text, zero network calls
$LIT open <work_id> --head 20000     # first N characters
$LIT extract <work_id>               # PDF → text, once; tries pdfplumber then pypdf
$LIT extract <work_id> --engine pypdf
```

`open` fails with exit 3 rather than silently fetching: if you want the network, say
so with `get`. If extraction reports a short result, the PDF is probably image-only —
use the harness's OCR/PDF skill (`liteparse`) rather than assuming the text is empty.

## inspect

```bash
$LIT show <work_id>            # resolved fields + which source supplied each
$LIT show <work_id> --raw      # the stored record verbatim
$LIT search-local "attention" --venue NeurIPS --with-pdf -n 20
$LIT library stats             # counts, size, year range, conflicts, pending merges
$LIT library list -n 50
$LIT library merges            # duplicate candidates awaiting a decision
$LIT evidence -n 10            # raw response snapshots
$LIT evidence --id ev_arxiv_x  # one snapshot, with a body preview
$LIT ledger -n 30              # append-only audit trail
```

`show` is the command to use when a field matters: `claim_conflicts` shows every
disagreeing value and its source instead of hiding the disagreement.

## ask / index — answer from the corpus, with anchors

```bash
$LIT ask "how does scaled dot-product attention work" -n 5
$LIT ask "what ablation did they run" --ids <work_id> -q 3   # restrict to one paper
$LIT index                        # rebuild passage indexes for stored full texts
$LIT index --ids <work_id>
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
$LIT cite arxiv:1706.03762
$LIT cite 10.1145/3292500.3330701 --format ris
$LIT cite <work_id> --format csl --key-style key
```

Returns the rendered entry plus `provenance` (which source asserted each field) and
`unavailable_fields` (which no source provided). Both matter: a field missing from the
entry is a fact about the metadata, not a tool failure — nothing is ever guessed.

## MCP server

```bash
python lit-mcp.py --library ./papers      # serve over stdio
python lit-mcp.py --list-tools            # inspect the exposed tools
```

Nine tools: `lit_contract`, `lit_channels`, `lit_find`, `lit_get`, `lit_ask`,
`lit_open`, `lit_cite`, `lit_export`, `lit_stats`. Newline-delimited JSON-RPC 2.0 over
stdio, no SDK and no extra dependency. Register it with any MCP client:

```json
{"mcpServers": {"lit": {"command": "python", "args": ["/path/to/lit-mcp.py", "--library", "/path/to/papers"]}}}
```

Because the CLI and the MCP server are both thin adapters over one core, they cannot
disagree: identical identity rules, identical dedup, identical legal policy. A result
obtained over MCP can be reproduced verbatim from a shell.

Tool failures are returned as data (`{"ok": false, "error": "no_fulltext", ...}`)
rather than as opaque protocol errors, so a caller can read the reason and adapt.



```bash
$LIT check --all                    # re-query only the decisive endpoints
$LIT check <id1>,<id2> -n 5
$LIT check-files                    # PDFs on disk vs recorded sha256; finds orphans
```

`check` is three-valued per record: `changed`, `unchanged`, or `unverifiable`. Absence
of a retraction notice is reported as **"not found in the sources checked"** — never as
"not retracted", because a miss is not evidence.

## verify — incremental re-verification

```bash
$LIT check --all                    # re-query only the decisive endpoints
$LIT check <id1>,<id2> -n 5
$LIT check-files                    # PDFs on disk vs recorded sha256; finds orphans
```

`check` is three-valued per record: `changed`, `unchanged`, or `unverifiable`. Absence
of a retraction notice is reported as **"not found in the sources checked"** — never as
"not retracted", because a miss is not evidence.

## citations

```bash
$LIT export --format bibtex -o refs.bib
$LIT export --format bibtex --ids <id1>,<id2>
$LIT export --format ris
$LIT export --format csl            # CSL-JSON for citation processors
$LIT export --format text --query "transformer"      # filter by title/abstract
$LIT export --key-style key          # DOI-derived keys instead of author-year
```

Citation keys are **stable across exports** (derived from identity, not list position),
so `\cite` commands survive re-export. Missing fields are omitted, never invented —
no guessed volume, page range or DOI.

## maintenance

```bash
$LIT doctor                  # consistency report: index freshness, unreadable files
$LIT doctor --repair         # same, rebuilding derived artefacts
$LIT repair                  # force a full rebuild of derived artefacts
$LIT reindex                 # usually unnecessary: commands self-check and rebuild
$LIT merge <keep_id> <drop_id>   # confirm a flagged duplicate
$LIT add-file ./paper.pdf --title "..." --authors "A One;B Two" --year 2024 --extract
```

`doctor`/`repair` never delete or rewrite `works/*.json`; the worst case is a rebuild.

## Worked example: a topic, end to end

```bash
# 1. Local first — free if you have already looked at this topic.
$LIT find "speculative decoding for LLM inference" -n 8

# 2. Acquire the ones you need (idempotent; only fetches what is missing).
$LIT get openreview:abcDEF123 --with-pdf --extract
$LIT get 10.48550/arXiv.2211.17192 --with-pdf

# 3. Read from disk — no network, and it works offline afterwards.
$LIT open openreview:abcDEF123 --head 40000

# 4. Answer with page-anchored evidence, then quote the anchors.
$LIT ask "what is the acceptance rate of speculative tokens"

# 5. Cite.
$LIT export --format bibtex --query "speculative decoding" -o related-work.bib
```

Second time round, step 1 answers from the corpus, step 2 is an instant local read, and
steps 3–5 never touch the network. That is the entire point of the tool.
