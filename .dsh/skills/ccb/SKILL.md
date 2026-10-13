---
name: ccb
description: "Aggregate every paper search/download channel (free APIs, keyed APIs, MCP servers, local CLI tools) behind one entry point, and maintain a durable local paper library so the same paper is never searched, downloaded and parsed twice. Use for: finding papers, downloading open-access PDFs, reading a paper's full text offline, building a reusable literature corpus, re-verifying stored records, exporting citations, and mining the corpus for a research topic with its evidence. 触发：找论文、搜文献、下载论文、读论文原文、建论文库、整理文献、导出引用、BibTeX、查文献是否撤稿、挖课题、选题、找创新点、课题生成。"
whenToUse: "Use when the user asks to find, download, read, organize or re-verify academic papers, build a reusable local paper corpus, export citations, or mine a research topic with evidence. Prefer over raw web search for paper discovery."
license: MIT
compatibility: "Needs network access for channel queries and corpus top-up (not for local reads). Python 3.10+ standard library only; PDF text extraction uses pdfplumber or pypdf when present. No credentials required — keyed channels degrade and say so. Optional keys raise rate limits only."
metadata:
  version: "0.3.0"
  tool: ccb
allowed-tools: Read Bash Write
---

# ccb — three modules: search, library, topics

`ccb` answers three questions: **"how do I get this paper"**, **"why am I downloading
it again"**, and **"what should I work on next"**. The second one is why the library
exists; the third is why it is worth keeping.

## The rule that matters

**Never edit the library by hand, and never re-run a pipeline you already ran.**
Every mutation goes through a `ccb` command, which writes the record file, the index
and the audit ledger together. Ask the library first; only go to the network on a miss.

## Call it like this

The tool and the corpus it builds live in the **same directory** — you clone the repo
and work in it:

```bash
CCB="python /path/to/ccb-assistant/ccb.py"   # the checkout's own entry point
$CCB find "diffusion models for molecule generation" -n 10
```

The library defaults to **`<checkout>/papers`**: inside the clone, and unaffected by
the working directory you call from. `--library <dir>` or `$CCB_HOME` override it —
use one of those to keep several corpora apart.
All commands print **JSON on stdout**; prose goes to stderr. Add `--pretty` **before**
the subcommand for humans (`$CCB --pretty doctor`).

**Exit codes** — branch on these instead of parsing text:
`0` ok · `2` usage · `3` not found · `4` partial (some channels failed, or the corpus is
too thin to mine) · `5` failed.
`ask` exits `0` when the corpus does not cover the question and reports
`"outcome": "not-covered"`: a coverage gap is an outcome to report, not a failed command.

## The canonical sequence

1. **Look locally first — always.**

   ```bash
   $CCB find "<topic>" -n 10
   ```
   Local hits are returned without touching the network. Only a miss goes to channels.

2. **Acquire what is missing** (idempotent — re-running costs nothing):

   ```bash
   $CCB get <work_id|DOI|arXiv id|OpenReview id|PMID|URL> --with-pdf
   ```
   `--with-pdf` also extracts and stores the text, so step 3 works offline
   immediately. Add `--extract` to extract a PDF that is already local but
   unextracted.

3. **Read from local storage, never re-download:**

   ```bash
   $CCB open <work_id> --head 20000     # zero network calls
   ```

4. **Answer from the corpus, with verifiable anchors:**

   ```bash
   $CCB ask "<question>" -n 5
   ```
   Returns ranked passages with `work_id` + `page` anchors — **not** generated prose.
   Compose the answer yourself and cite the anchors. If `grounded` is false, say the
   corpus does not cover the question; never answer from memory.

5. **Export citations** (fields with no source are omitted, never invented):

   ```bash
   $CCB cite <work_id>                        # one entry + which source gave each field
   $CCB export --format bibtex --ids <work_id>,<work_id> -o refs.bib
   ```

## Generating a research topic

`ccb topics` mines the corpus for **one topic at a time**. It returns evidence and
structure, never prose: every claim is anchored to a `work_id` + page.

```bash
$CCB topics survey "<direction>"        # 1. map the corpus; tops it up if too thin
$CCB topics gaps <survey_id>            # 2. the evidence: author statements + statistics
$CCB topics candidates <survey_id>      # 3. ranked (evidence × novelty operator)
$CCB topics draft <candidate_id>        # 4. commit to ONE; returns the section skeleton
#    ... write each section from the anchors attached to it ...
$CCB topics rate <topic_id> [--venue X] # 5. CCF estimate: bound, band, basis, risks
$CCB topics save <topic_id>             # 6. commit, export Markdown, retire the key
$CCB topics list                        # what is already mined
$CCB topics venues --verify             # the CCF catalogue
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

## Reading results

Every record carries its provenance. Trust and quote it (a sample record with
`field_sources` and `conflicts` is in `references/commands.md`):

- `work_id` is **stable** — hand it back verbatim in later calls.
- `conflicts` lists fields where sources disagree. Report the disagreement; do not
  silently pick one.
- `errors` maps a channel name to why it produced nothing. **"Nothing found" and
  "could not look" are different facts.** Say which one happened.

## How to phrase results

- **Never call an abstract or a metadata record "the full text"** — full-text status is
  what `has_fulltext` / `outcome` says.
- **Discover, don't assume** — check `ccb channels` / `ccb contract` for what a source
  offers and which flags exist, instead of guessing from other tools.
- **Prefer a targeted query when the field is clear** (`-s arxiv,crossref`); keep
  multi-source fan-out for genuinely broad questions.

## When a credential is missing

Trigger: `channels_unavailable` is non-empty, or `errors` mentions `missing credential:`.

1. **Say what happened.** Name the channel and quote the reason as given — do not soften it
   into "a network problem".
2. **Say what it costs.** `ccb channels` → `credentials_missing[<channel>].kind`:
   `required` = the source cannot be used at all; `optional` = it only raises rate limits.
3. **Give the next step.** Name the environment variable and the command to re-run, then
   carry on with the channels that do work and state the coverage gap (exit `4`).

Never ask the user to paste a key into the conversation — a value that enters the
conversation enters the context and any log; ask them to set the variable themselves.
Never report "no papers found" when the truth is "could not look", and never retry a
channel in a loop.

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

`-s auto` already prefers CS authorities and skips channels that cannot handle the
identifier you gave. The routing table lives in `ccb contract`; per-source traps and
gating live in `references/channels.md`.

## Full detail

- `docs/for-agents.md` — written for agents: faces, context cost, rules
- MCP face: 16 `ccb_*` tools — registration in `references/commands.md`
- `references/commands.md` — every command and flag, with examples
- `references/topics.md` — the operators, the scoring, the CCF estimate
- `references/architecture.md` — the three modules, on-disk layout, local-first
- `references/channels.md` — per-source contracts, measured behaviour, known traps
