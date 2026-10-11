---
name: lit
description: "Aggregate every paper search/download channel (free APIs, keyed APIs, MCP servers, local CLI tools) behind one entry point, and maintain a durable local paper library so the same paper is never searched, downloaded and parsed twice. Use for: finding papers, downloading open-access PDFs, reading a paper's full text offline, building a reusable literature corpus, re-verifying stored records, and exporting citations. 触发：找论文、搜文献、下载论文、读论文原文、建论文库、整理文献、导出引用、BibTeX、查文献是否撤稿。"
license: MIT
compatibility: "Needs network access for channel queries (not for local reads). Python 3.10+ standard library only; PDF text extraction uses pdfplumber or pypdf when present. No credentials required — keyed channels degrade and say so. Optional keys raise rate limits only."
metadata:
  version: "0.1.0"
  tool: lit
allowed-tools: Read Bash Write
---

# lit — one entry point for every paper channel, plus a durable local library

`lit` answers two questions: **"how do I get this paper from any source"** and
**"why am I downloading it again"**. The second one is the point.

## The rule that matters

**Never edit the library by hand, and never re-run a pipeline you already ran.**
Every mutation goes through a `lit` command, which writes the record file, the index
and the audit ledger together. Ask the library first; only go to the network on a miss.

## Call it like this

```bash
LIT="python /path/to/tools/lit-skill.py"   # or just `lit` if installed
$LIT --library ./papers find "diffusion models for molecule generation" -n 10
```

`--library <dir>` (or `$LIT_HOME`) chooses the corpus; default is `./.lit`.
All commands print **JSON on stdout**; prose goes to stderr. Add `--pretty` for humans.

**Exit codes** — branch on these instead of parsing text:
`0` ok · `2` usage · `3` not found · `4` partial (some channels failed, results exist) ·
`5` failed.

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

## Command reference

| Command | Purpose |
|---|---|
| `channels [name]` | Every channel, whether it is usable, and which env var it is missing |
| `contract` | The operating rules and step order, machine-readable |
| `find <query> [-n N] [-s auto\|all\|a,b] [--min-local N]` | Local first, then channels |
| `get <id> [--with-pdf] [--extract\|--refresh] [-s ...]` | Acquire one paper |
| `ask "<question>" [-n N] [--ids ...]` | Retrieve page-anchored passages |
| `open <id> [--head N]` | Read stored full text (never hits the network) |
| `index [--ids ...]` | Rebuild the passage index for stored full texts |
| `show <id> [--raw]` | One record incl. **which source supplied each field** |
| `search-local [query] [--venue V] [--author A] [--with-pdf]` | Query only the corpus |
| `cite <id> [--format bibtex\|ris\|csl\|text]` | One citation + field provenance |
| `check <ids>\|--all` | Re-verify: new version, OA change, retraction |
| `check-files` | Verify stored PDFs against their recorded hashes |
| `library stats\|report\|list\|merges` | Corpus views and pending duplicate candidates |
| `export --format bibtex\|ris\|csl\|text [--ids ...] [--query ...]` | Citations |
| `add-file <pdf> [--title ...]` | Put a PDF you already have into the library |
| `doctor` / `repair` | Consistency report / rebuild derived artefacts |
| `merge <keep> <drop>` | Confirm a duplicate that was only flagged |
| `evidence [--id EVID]` / `ledger` | Raw response snapshots / append-only audit trail |

Useful flags: `--offline` (fail rather than reach the network), `--pretty`,
`--channel a,b` (allow-list), `--disable-channel dblp`.

## Also available over MCP

The same core is exposed as an MCP server with tools `lit_contract`, `lit_channels`,
`lit_find`, `lit_get`, `lit_ask`, `lit_open`, `lit_cite`, `lit_export`, `lit_stats` —
one core, several faces, identical behaviour to the CLI. See
`references/commands.md` for how to start and register it.

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

Notes that save time:
- **arXiv's relevance ranking is loose** — treat it as an identifier and full-text
  source, not a ranking engine.
- **`dblp` is often gated** by an anti-bot challenge; the tool reports this and
  degrades. Do not treat its silence as "no such paper".
- **Semantic Scholar 429s** without a key; it is a supplement, not a dependency.

## Full detail

- `references/architecture.md` — layers, on-disk layout, why local-first works
- `references/channels.md` — per-source contracts, measured behaviour and known traps
- `references/commands.md` — every flag with copy-paste examples
