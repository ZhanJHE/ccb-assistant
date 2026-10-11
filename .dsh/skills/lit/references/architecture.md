# Architecture

## The problem being solved

Every AI session that touches literature repeats the same cycle:

```
ask → search the web → download a PDF → extract text → put it in context → discard
ask again → search again → download again → extract again → discard
```

Nothing is retained, so nothing accumulates. Existing tools cover *finding* papers
extremely well (several mature 20+ source aggregators) but all discard the identity
map after each query, which means the same paper re-discovered next week is a new
record. This tool exists to break that cycle.

## Four layers plus one protocol

```
L4  citations   BibTeX / RIS / CSL-JSON / plain text
L3  extraction  PDF → stored text (reuses pdfplumber/pypdf; does not reimplement)
L2  library     durable local corpus: stable ids, dedup, provenance, evidence
L1  channels    one interface over free APIs, keyed APIs, MCP servers, local CLIs
──────────────────────────────────────────────────────────────────────────
★   local-first protocol: every request consults L2 before L1
```

The local-first protocol is the load-bearing part:

```
get(identifier):
    hit = library.resolve(identifier)          # local, zero network
    if hit is complete:      return hit        # nothing re-fetched, re-parsed
    if hit lacks full text:  fetch only that   # metadata is not re-queried
    else:                    L1 → store → return
```

Measured on a real paper (arXiv 1706.03762, a 2.2 MB PDF):

| Pass | Time | Network |
|---|---|---|
| First `get --with-pdf` | ~5–7 s | channels queried, PDF downloaded, stored |
| Second `get --with-pdf` | **0.2 s** | **none** — "Answered from the local library" |
| `get --offline` | 0.2 s | none |
| Same paper by its DOI instead of its arXiv id | 0.2 s | none — resolves to the same `work_id` |

## On-disk layout

```
library/
  library.json                 # schema, work count, index fingerprint
  works/<2>/<2>/<work_id>.json # authoritative record  ← the source of truth
  evidence/<ev_id>.json        # raw channel response, before parsing
  files/<2>/<sha256>.pdf       # content-addressed: identical bytes stored once
  blobs/<work_id>/fulltext.txt # extracted text
  library.jsonl                # append-only event ledger
  index.sqlite                 # derived query index — deletable, always rebuildable
  channels.yaml                # optional: declare extra channels without code
```

**Why plain text is the truth source rather than SQLite directly:** the corpus stays
diffable, greppable, hand-inspectable and committable, and a damaged index can never
destroy data — the worst case is a slow rebuild. `index.sqlite` is a cache.

## Identity: two layers, both deterministic

```
work_id        the conceptual paper        "which paper is this"
manifestation  a specific carrier          arXiv v2 / NeurIPS camera-ready / journal version
```

A `work_id` comes from an **explicit ordered key chain**, not from probabilistic
matching, and the key that matched is recorded for audit:

| Rank | Key | Example |
|---|---|---|
| 1 | `doi` | `doi:10.1145/3292500.3330701` |
| 2 | `openreview` | `openreview:abcDEF123` |
| 3 | `arxiv` | `arxiv:1706.03762` |
| 4 | `acl` / `pmlr` / `dblp` | `pmlr:97:1` |
| 5 | `t:<norm title>|<first author>|<year>` | last resort |

Deliberate detail: an **arXiv DOI** (`10.48550/arxiv.X`) never outranks the arXiv id
it was minted from. Otherwise a preprint's identity would depend on which channel
happened to supply a DOI, and the same paper would be stored twice.

Manifestations exist so that an arXiv v2 and a NeurIPS camera-ready are **one work
with two carriers** — distinct PDFs and page numbers, one citation target. Tools that
collapse this either duplicate the paper or lose version information.

## Provenance: claims, never overwrites

A field is an ordered list of claims, each naming its source, timestamp and evidence
snapshot:

```json
"title": [
  {"src": "arxiv", "val": "Attention Is All You Need", "at": "…", "ev": "ev_arxiv_…"},
  {"src": "paper_search", "val": "Attention Is All You Need", "at": "…", "ev": "ev_…"}
]
```

The display value follows source trust (publisher of record > dblp > arXiv >
aggregators), but **every claim survives**, so a disagreement about a year or a volume
number is *visible* rather than silently resolved. `lit show <id>` prints the
conflicts; `field_sources` in every result says who supplied what.

## Deduplication: conservative by construction

1. **Exact stage** — any shared strong key means the same work.
2. **Fuzzy stage** — normalized title token Jaccard + first author + year tolerance,
   with blocking so the comparison is not O(n²).

Only **near-identical** records merge automatically (Jaccard ≥ 0.92 plus corroborating
signals). Everything in the plausible band becomes an auditable `merge_candidate` for
an explicit `lit merge`. A wrong automatic merge would silently corrupt every citation
downstream, which is a far worse outcome than one extra candidate to review.

## L4: why retrieval is bounded this way

Having a PDF on disk is not the same as being able to answer from it. Without a
retrieval layer, an agent either reads whole papers into context or, worse, answers
from memory. So `ask` does the deterministic half of retrieval-augmented answering and
stops there:

- **chunk** stored full text into ~1200-character overlapping passages, remembering the
  page each came from;
- **rank** with BM25 (Okapi, k1=1.5 b=0.75) over a pure-standard-library index — no
  model download, no network, no API key, and identical output for identical input;
- **return evidence**: passage text plus `work_id`, page, character offsets, and a
  ready-made citation string.

It deliberately does **not** generate prose. Summarising is the caller's job; supplying
checkable anchors is this tool's job. That boundary is what makes a citation verifiable
rather than plausible.

Three decisions worth recording:

- **Page anchors come from the extraction step**, which splits on the form feeds the PDF
  engines emit. When no form feed is present the whole document is reported as page 1
  rather than inventing pagination.
- **Deterministic ranking is a feature, not a limitation.** A stable order means the same
  question yields the same citations, so a reader can reproduce them.
- **`grounded: false` is a first-class answer.** "The corpus does not cover this" is
  reported instead of being padded with the least-bad passage.

## Extraction: choosing per page, not per file

Measured on one real paper, the two available extractors disagreed in opposite
directions: `pdfplumber` returned the complete body (35k chars) with words jammed
together, and `pypdf` returned cleanly spaced text but only 9k chars, announcing
"Rotated text discovered. Output will be incomplete."

Picking one engine globally forces a bad trade — clean-but-truncated or
complete-but-unreadable. So each page is scored for word-separation health and the best
strategy *for that page* wins, then pages are stitched back together. The same paper
yielded 61k characters at a 0.99 quality score, using `pdfplumber -layout` on two pages,
`pypdf` on twelve and `pypdf -layout` on one. A heuristic space-repair is applied only
where no strategy managed clean spacing, and the result is reported rather than hidden.

## Three faces, one core

```
                    ┌─────────────────────────┐
   CLI (JSON)  ────►│                         │
   Agent Skill ────►│   Library + Resolver    │
   MCP server  ────►│   (the only behaviour)  │
                    └─────────────────────────┘
```

Each face is a thin adapter. There is no CLI-specific or MCP-specific logic, which is
why they cannot disagree about identity, deduplication policy, or what counts as a
legal source. The test suite pins this: `tests/test_mcp.py` asserts that the same `ask`
and the same `stats` produce the same answers through both faces.

## Why the index self-heals


An agent will eventually skip a step or edit a file. Rather than relying on
discipline, every command runs a cheap consistency check first:

- index missing / stale / built from a different set of work files → **rebuilt
  automatically** from the JSON files;
- a work file that will not parse → **reported**, never deleted, and skipped so one
  damaged record cannot take the corpus down;
- merged or re-identified works → their derived index rows are removed so an old
  identifier does not resolve to a record that no longer exists.

`Library.save()` is the single write path, so the record file, the index and the ledger
cannot diverge. `lit doctor` reports; `lit repair` rebuilds everything derived. Neither
ever rewrites or deletes `works/*.json`.
