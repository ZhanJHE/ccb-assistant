# ccb for AI agents

You are an AI agent that has found ccb, probably because a user wants to find, download,
or organise academic papers. This page is the single place to learn how. It is written
for you; the [README](../README.md) is written for people.

## Two faces, one core

| Face | What it is | Context cost | Use it when |
|---|---|---|---|
| `python ccb.py …` | A CLI with 23 commands; JSON on stdout, meaningful exit codes | **zero until used** | **You can run shell commands.** This is the default answer. |
| `ccb-mcp.py` | An MCP server exposing 16 `ccb_*` tools | ~1.5k tokens of tool schema on every request (6166 characters of schema JSON; kept in sync by `tests/test_docs.py`) | Your client speaks MCP but has no shell. |

Both read the same library and cannot disagree — they are derived from one operation
table. The CLI exposes strictly more (per-command flags like `--compact`, `--raw`,
`--min-local` have no tool equivalents).

## The three rules that matter

1. **Rules come from the tool, not from memory.** Run `python ccb.py contract` (or
   `ccb_contract` over MCP) first — it is machine-readable and cannot drift.
2. **Local before network.** `find` already consults the local library; a hit costs no
   network. Do not bypass it with another search tool.
3. **No prose, no invented citations.** `ask` returns passages with `work_id` + page
   anchors; compose the answer from them and cite the anchors. When
   `outcome` is `"not-covered"`, say the corpus does not cover the question.

## If a credential is missing

`channels_unavailable` / `errors` name the channel and the reason. `ccb channels` →
`credentials_missing[<channel>]` tells you whether the key is `required` (source unusable)
or `optional` (rate limits only). Tell the user which **environment variable** to set and
what it buys — never take a key value through the conversation. Then carry on with the
channels that work and state the coverage gap (exit `4`).

## Teaching this tool to a project

If the user wants ccb available in *their* project, run:

```bash
python ccb.py install-skill          # copies the skill into ./.dsh/skills/ccb
python ccb.py install-skill --global # or into ~/.dsh/skills/ccb
```

The skill is what makes an agent use this tool without the rules being re-explained.

## Canonical sequences

The `workflows` section of `python ccb.py contract` holds the exact step order for the
four things agents do most: answer a question from the corpus, find then read a topic,
build a bibliography, and generate a research topic. Follow it; every step names its
command so you do not have to choose.
