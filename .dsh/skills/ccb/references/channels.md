# Channels

A *channel* is any source of paper records or files: a free HTTP API, a keyed
commercial API, an MCP server, a local CLI tool, or a file the user supplies.

The point of the abstraction is **transparency**. A channel that needs a credential
you do not have does not fail the request — it reports itself unavailable, names the
environment variable, and the others carry on. A channel that is gated or rate-limited
does not return an empty result that reads like "nothing exists" — it says what
happened. `ccb channels` lists the current state; `errors` in any result maps a
channel name to its reason.

## Measured availability from this machine

Probed live while building this tool. Treat these as observations with a date, not as
permanent facts — re-run `ccb channels` to re-check.

| Channel | Status | Notes |
|---|---|---|
| `openalex` | ✅ works keyless | Broadest index; best open-access locator. `OPENALEX_API_KEY` raises the daily budget, `OPENALEX_EMAIL` joins the polite pool |
| `crossref` | ✅ works keyless | Publisher of record: container title, volume, issue, pages |
| `arxiv` | ✅ works | 3 s/request etiquette enforced; **intermittently answers 404 under load** — retried automatically |
| `europepmc` | ✅ works keyless | No key, no email; dependable fallback; indexes biomedical preprints |
| `openreview` | ✅ works keyless | Stable identity for CS conference papers with **no DOI** |
| `unpaywall` | ✅ works | Requires a real `email`; placeholders are rejected |
| `doaj`, `core` | ✅ reachable | Optional keys raise limits |
| `paper_search` | ✅ if installed | Bridge to a local multi-source CLI (21 sources) |
| `dblp` | ⚠️ **gated** | Fronted by an Anubis anti-bot challenge that answers **HTTP 200 with an HTML page**. Retrying does not help and would be circumvention; the channel reports the gate and the query degrades to other channels |
| `semantic_scholar` | ⚠️ 429 keyless | Genuinely rate-limited without `S2_API_KEY`; a supplement, not a dependency |
| Google Scholar | ❌ not offered | Scraping violates its ToS and the anti-bot is unsolved |

## Traps this tool handles explicitly

These are the failure modes that produce *confident wrong answers*, which is worse
than an error. Each one was observed, not theorised.

**A 200 is not success.** arXiv returns an Atom feed containing one entry titled
`Error` for a malformed query; Europe PMC puts `errCode` in a 200 body; DBLP's
challenge page is HTML with status 200. Parsing naively turns each of these into a
plausible-looking result set.

**A search index can answer a precise query with the wrong paper.** OpenAlex's
`filter=doi:10.48550/arxiv.1706.03762` returns `count=1` — for a work whose own DOI is
`10.65215/2q58a426` and whose title merely coincides. Accepting that would attach a
stranger's DOI to the requested paper. Every channel result therefore passes through
`verify_identifier`: a record that does not actually carry the identifier asked about
is **discarded**, with the reason reported, rather than stored.

**A loose full-text search is not an identifier lookup.** On OpenAlex,
`search=1706.03762` returns ~15,000 hits and `search=10.48550/arxiv.X` returns ~6,000.
Identifiers are therefore never passed as free text; an arXiv id resolves through its
registered DOI, and when nothing matches precisely the channel declines.

**A PDF content-type does not make a PDF.** Publishers and repositories return HTML
landing pages, JSON errors and bot challenges under a PDF content type, so the payload
is verified by its `%PDF-` magic bytes before anything is stored.

**Versioned URLs are not identity.** arXiv advertises `/pdf/1706.03762v7`; the URL is
normalized to the versionless form, or every new arXiv version would look like a
changed record.

**Credentials can be in the URL.** Several scholarly APIs authenticate by query string,
so the URL *is* a secret. Redaction happens at write time, so a key can never reach
disk, let alone output.

## Routing

`-s auto` (the default) prefers CS authorities and skips channels that cannot handle
the identifier given (an arXiv id is never sent to a DOI-only resolver).

| Job | Primary | Also |
|---|---|---|
| CS conference paper, maybe no DOI | `openreview` | `dblp` when reachable, `openalex` |
| Journal article | `crossref` | `openalex` |
| Preprint / LaTeX source | `arxiv` | `openalex` |
| Legal OA PDF | `openalex` OA locations | `arxiv` |
| Broad topic discovery | `openalex`, `crossref` | — |
| Biomedicine / clinical ML | `europepmc` | `pubmed` |
| Citation graph | `semantic_scholar` (key) | `openalex` |

## Adding a channel without writing code

Declare it in `<library>/channels.yaml` (or point `$CCB_CHANNELS` at a file):

```yaml
channels:
  dblp_mirror:
    kind: http
    title: "dblp mirror"
    url: "https://example.org/api?q={query}&n={limit}"
    caps: [search, lookup]
    auth: env:MY_API_KEY?          # '?' marks it optional
    auth_header: Authorization
    auth_value: "Bearer {key}"
    rate_rps: 1.0
    limit_param: n
    query_param: q
    map:
      items: result.hits.hit
      total: result.hits.@total
      title: info.title
      authors: info.authors.author
      author_name: text
      year: info.year
      venue: info.venue
      doi: info.doi
      url: info.url
```

`kind` can be `http`, `cli` (wrap an installed command) or `mcp` (stdio JSON-RPC).
Dot paths support `a.b.0.c`, `a.*.c` and `@key` (recursive search), because envelope
depth varies between APIs. An unmapped or missing field yields an empty value rather
than an exception: a partially-mapped source is still useful, a crashing one is not.

## Legal and safety baseline

Non-negotiable, and enforced by what the tool does *not* implement:

- **Open access and publisher-sanctioned routes only.** No Sci-Hub, no Anna's Archive.
  (Several widely-used tools embed these; this one deliberately does not.)
- **No circumvention.** When a source is gated by an anti-bot challenge, that is
  reported as a fact, not worked around.
- **No scraping of ToS-protected indexes.** Google Scholar is not offered.
- **Credentials are read from the environment only**, never written to records,
  evidence, logs or output.
- When no legal PDF exists, say so plainly rather than hunting a mirror.
