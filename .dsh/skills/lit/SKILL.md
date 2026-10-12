---
name: lit
description: "Aggregate every paper search/download channel (free APIs, keyed APIs, MCP servers, local CLI tools) behind one entry point, and maintain a durable local paper library so the same paper is never searched, downloaded and parsed twice. Use for: finding papers, downloading open-access PDFs, reading a paper's full text offline, building a reusable literature corpus, re-verifying stored records, exporting citations, and mining the corpus for a research topic with its evidence. 触发：找论文、搜文献、下载论文、读论文原文、建论文库、整理文献、导出引用、BibTeX、查文献是否撤稿、挖课题、选题、找创新点、课题生成。"
license: MIT
compatibility: "Needs network access for channel queries and corpus top-up (not for local reads). Python 3.10+ standard library only; PDF text extraction uses pdfplumber or pypdf when present. No credentials required — keyed channels degrade and say so. Optional keys raise rate limits only."
metadata:
  version: "0.2.0"
  tool: lit
allowed-tools: Read Bash Write
---

# lit — three modules: search, library, topics

`lit` answers three questions: **"how do I get this paper"**, **"why am I downloading
it again"**, and **"what should I work on next"**. The second one is why the library
exists; the third is why it is worth keeping.

## The rule that matters

**Never edit the library by hand, and never re-run a pipeline you already ran.**
Every mutation goes through a `lit` command, which writes the record file, the index
and the audit ledger together. Ask the library first; only go to the network on a miss.

## Call it like this

The tool and the corpus it builds live in the **same directory** — you clone the repo
and work in it:

```bash
LIT="python /path/to/ccb-assistant/lit.py"   # the checkout's own entry point
$LIT find "diffusion models for molecule generation" -n 10
```

The library defaults to **`<checkout>/papers`**: inside the clone, and unaffected by
the working directory you call from. `--library <dir>` or `$LIT_HOME` override it —
use one of those to keep several corpora apart.
All commands print **JSON on stdout**; prose goes to stderr. Add `--pretty` **before**
the subcommand for humans (`$LIT --pretty doctor`).

**Exit codes** — branch on these instead of parsing text:
`0` ok · `2` usage · `3` not found · `4` partial (some channels failed, or the corpus is
too thin to mine) · `5` failed.

## The canonical sequence

1. **Look locally first — always.**

   ```bash
   $LIT find "<topic>" -n 10
   ```
   Local hits are returned without touching the network. Only a miss goes to channels.

2. **Acquire what is missing** (idempotent — re-running costs nothing):

   ```bash
   $LIT get <work_id|DOI|arXiv id|OpenReview id|PMID|URL> --with-pdf
   ```
   `--with-pdf` also extracts and stores the text, so step 3 works offline
   immediately. Add `--extract` to extract a PDF that is already local but
   unextracted.

3. **Read from local storage, never re-download:**

   ```bash
   $LIT open <work_id> --head 20000     # zero network calls
   ```

4. **Answer from the corpus, with verifiable anchors:**

   ```bash
   $LIT ask "<question>" -n 5
   ```
   Returns ranked passages with `work_id` + `page` anchors — **not** generated prose.
   Compose the answer yourself and cite the anchors. If `grounded` is false, say the
   corpus does not cover the question; never answer from memory.

5. **Export citations** (fields with no source are omitted, never invented):

   ```bash
   $LIT cite <work_id>                        # one entry + which source gave each field
   $LIT export --format bibtex --ids <work_id>,<work_id> -o refs.bib
   ```

## Generating a research topic

`lit topics` mines the corpus for **one topic at a time**. It returns evidence and
structure, never prose: every claim is anchored to a `work_id` + page.

```bash
$LIT topics survey "<direction>"        # 1. map the corpus; tops it up if too thin
$LIT topics gaps <survey_id>            # 2. the evidence: author statements + statistics
$LIT topics candidates <survey_id>      # 3. ranked (evidence × novelty operator)
$LIT topics draft <candidate_id>        # 4. commit to ONE; returns the section skeleton
#    ... write each section from the anchors attached to it ...
$LIT topics rate <topic_id> [--venue X] # 5. CCF estimate: bound, band, basis, risks
$LIT topics save <topic_id>             # 6. commit, export Markdown, retire the key
$LIT topics list                        # what is already mined
$LIT topics venues --verify             # the CCF catalogue
```

Rules:

- **One topic per `draft`.** Its `dedup_key` is retired, so the same combination is
  never proposed again. That is what stops repeated mining from producing the same
  idea in new words.
- **Compose every section from the anchors attached to it.** If a claim has no anchor,
  drop the claim. A reference may only come from `references` in the draft — never
  from memory.
- **`rate` is a rule-based estimate with its reasoning, not an acceptance prediction.**
  Report the basis and the risks alongside the band.
- **If `survey` reports `sufficient: false` (exit 4), say so and stop.** Do not lower
  the bar in order to produce a topic. A gap claim the corpus cannot support is worse
  than no topic.
- Datasets and baselines in the draft are **observed mentions with counts**, not
  recommendations. Verify availability before committing to one.

## Also available over MCP

The same core is exposed as an MCP server with 16 tools: `lit_contract`, `lit_channels`,
`lit_find`, `lit_get`, `lit_ask`, `lit_open`, `lit_cite`, `lit_export`, `lit_stats`, and
the seven `lit_topics_*` tools that mirror the sequence above — one core, several faces,
identical behaviour to the CLI. See `references/commands.md` for how to register it.

## Reading results

Every record carries its provenance. Trust and quote it:

```json
{"work_id": "arxiv:1706.03762", "has_pdf": true, "has_fulltext": true,
 "field_sources": {"title": ["arxiv", "paper_search"], "year": ["arxiv"]},
 "conflicts": ["venue"]}
```

- `work_id` is **stable** — hand it back verbatim in later calls.
- `conflicts` lists fields where sources disagree. Report the disagreement; do not
  silently pick one.
- `errors` maps a channel name to why it produced nothing. **"Nothing found" and
  "could not look" are different facts.** Say which one happened.

## Rules the tool enforces — work with them

- **Fields are never overwritten.** A new value becomes another claim; the display
  value follows source trust (publisher of record > dblp > arXiv > aggregators).
- **Only near-identical records merge automatically.** Everything ambiguous becomes a
  merge candidate in `library merges` for an explicit `merge`. A wrong merge corrupts
  every citation downstream, so confirm rather than assume.
- **Every channel response is snapshotted** under `evidence/` before parsing, which is
  why field provenance and offline replay work. Never re-fetch to audit something.
- **Legal routes only.** Open access and publisher-sanctioned access. No Sci-Hub, no
  Anna's Archive, no scraping of ToS-protected indexes. If a PDF is not freely
  available, report that — never hunt mirrors.
- **Credentials stay in the environment.** Never print, log or pass a key value; some
  APIs authenticate by query string, so the URL itself can be a secret.
- **Do not run `reindex` before queries.** Every command self-checks and rebuilds a
  stale index; a maintenance step you must remember is one that gets forgotten.

## Choosing a channel

`-s auto` (the default) already prefers CS authorities and skips channels that cannot
handle the identifier you gave. Override only for a reason:

| Job | Channel |
|---|---|
| CS conference paper, possibly no DOI | `openreview`, then `dblp` |
| Journal article | `crossref` (publisher of record), then `openalex` |
| Preprint or LaTeX source | `arxiv` |
| Legal open-access PDF | `openalex` OA locations, then `arxiv` |
| Broad topic discovery | `openalex`, `crossref` |
| Biomedicine / clinical ML | `europepmc` |

arXiv ranks loosely (an identifier source, not a ranking engine); `dblp` is often gated
and says so; Semantic Scholar 429s keyless.

## Full detail

- `references/commands.md` — every command and flag, with examples
- `references/topics.md` — the operators, the scoring, the CCF estimate
- `references/architecture.md` — the three modules, on-disk layout, local-first
- `references/channels.md` — per-source contracts, measured behaviour, known traps
