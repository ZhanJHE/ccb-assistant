"""The self-describing contract.

This module exists for one reason: an agent driving this tool will eventually skip a
step, reorder steps, or invent a step. The tool therefore states its own rules and
correct sequences in machine-readable form, and every command can return them.

The contract is the interface, not documentation prose that can drift away from the
code: the CLI, the Agent Skill and the MCP surface all read it from here.
"""

from __future__ import annotations

from typing import Any

from . import ops

# The rules the program enforces so the agent does not have to remember them.
INVARIANTS: list[dict[str, str]] = [
    {
        "id": "single-write-path",
        "rule": "Never edit files under the library by hand. Every mutation goes through a "
                "command; the program writes the work JSON, the index and the ledger together.",
        "why": "Hand edits desynchronise the index and the ledger from the truth on disk.",
    },
    {
        "id": "text-is-truth",
        "rule": "works/*.json is the source of truth; index.sqlite is derived and disposable.",
        "why": "Deleting or corrupting the index is always recoverable; editing it is not.",
    },
    {
        "id": "self-check-first",
        "rule": "Do not run 'reindex' before queries. Every command self-checks and rebuilds "
                "a stale index automatically.",
        "why": "A maintenance step that must be remembered is a step that will be forgotten.",
    },
    {
        "id": "local-first",
        "rule": "Query the local library before any network call. Only fall through to "
                "channels on a miss.",
        "why": "This is the whole point: never re-run search/download/extract for a paper "
               "the library already holds.",
    },
    {
        "id": "no-overwrite",
        "rule": "Fields are never overwritten. A new value is added as another claim and the "
                "display value is chosen by source trust order.",
        "why": "Overwriting destroys the ability to notice that two sources disagree.",
    },
    {
        "id": "conservative-dedup",
        "rule": "Only near-identical records auto-merge. Anything ambiguous is recorded as a "
                "merge candidate and left alone until confirmed.",
        "why": "A wrong merge silently poisons every citation that follows.",
    },
    {
        "id": "evidence-before-parse",
        "rule": "Every channel response is snapshotted under evidence/ before it is parsed.",
        "why": "Makes field provenance and offline replay possible; never re-fetch to audit.",
    },
    {
        "id": "never-answer-from-memory",
        "rule": "When answering a question from the corpus, build the answer only from "
                "passages returned by `ask`, and cite the work_id and page. If `grounded` is "
                "false, say the corpus does not cover it.",
        "why": "Unanchored answers about papers are indistinguishable from confabulation; "
               "the page anchor is what makes a claim checkable.",
    },
    {
        "id": "legal-sources-only",
        "rule": "Only open-access and publisher-sanctioned routes. No paywall circumvention, "
                "no Sci-Hub, no scraping of ToS-protected indexes.",
        "why": "Legal exposure and reproducibility both depend on it.",
    },
    {
        "id": "never-echo-secrets",
        "rule": "Credentials live in the library's credentials config "
                "(papers/credentials.yaml) and are redacted everywhere else: loaded "
                "values are registered and scrubbed from every snapshot, cache and "
                "report at write time. Never print, log or pass a key value.",
        "why": "Some APIs authenticate by query string, so a URL can itself be a secret. "
               "Value-based scrubbing catches it wherever it travels, not only in "
               "obvious parameters.",
    },
    {
        "id": "report-failures",
        "rule": "A channel that is gated, rate-limited or unavailable must be reported by name "
                "with a reason; never silently return an empty result.",
        "why": "'No results' and 'could not look' are different facts with different responses.",
    },
    {
        "id": "evidence-anchored-topics",
        "rule": "A topic claim is emitted only with an anchor into the corpus: a work_id, "
                "a page and the source sentence. The tool never writes prose.",
        "why": "A research idea whose support cannot be re-read is indistinguishable from "
               "one that was invented; the anchor is what makes an idea auditable.",
    },
    {
        "id": "one-topic-at-a-time",
        "rule": "`topics candidates` proposes; `topics draft` commits to exactly one and "
                "records its (gap evidence x novelty operator) key. That combination is "
                "never proposed again.",
        "why": "Mining the same gap repeatedly yields the same idea in new words, and a "
               "corpus of near-duplicate topics is worse than an empty one.",
    },
    {
        "id": "rating-is-estimate",
        "rule": "A CCF rating is reported as an upper bound, a band, its per-rule basis and "
                "a confidence — never as a promise. Every input to it must be recomputable.",
        "why": "A fabricated acceptance prediction is exactly the kind of invented fact this "
               "tool refuses to produce everywhere else.",
    },
]

# The three business modules, and the one shared floor beneath them. Declared here
# rather than in prose because the boundary is what the whole split is for: a module
# may import only what `depends_on` names.
#
# `cli` and `mcp` are derived from `ccb.ops` rather than listed by hand: they used to be
# a second copy of the command surface, kept in step by discipline alone, and a contract
# that names a command it does not have is worse than no contract.
MODULES: list[dict[str, Any]] = [
    {
        "name": "search",
        "package": "ccb.search",
        "role": "Find and obtain a paper from any source, by legal routes only.",
        "owns": [
            "the channel registry and every channel implementation (http/cli/mcp/manual)",
            "HTTP transport: rate limiting, retries, credential transparency",
            "the local-first acquisition protocol (get / find / re-check)",
        ],
        "depends_on": ["core", "library"],
        "cli": ops.cli_names("search"),
        "mcp": ops.mcp_names("search"),
    },
    {
        "name": "library",
        "package": "ccb.library",
        "role": "Keep a durable local corpus that cannot rot.",
        "owns": [
            "work records, raw evidence snapshots and the disposable query index",
            "grounded passage retrieval (ask) and citation export",
            "the single write path through which every mutation passes",
        ],
        "depends_on": ["core"],
        "cli": ops.cli_names("library"),
        "mcp": ops.mcp_names("library"),
    },
    {
        "name": "topics",
        "package": "ccb.topics",
        "role": "Mine the corpus for one research topic worth doing, with its evidence.",
        "owns": [
            "domain survey and gap-evidence extraction from stored full text",
            "novelty operators, novelty self-check and candidate ranking",
            "the CCF rating estimate and the draft skeleton",
        ],
        "depends_on": ["core", "library", "search"],
        "cli": ops.cli_names("topics"),
        "mcp": ops.mcp_names("topics"),
    },
]

CORE: dict[str, Any] = {
    "name": "core",
    "package": "ccb.core",
    "role": "The shared floor: records, identities, normalisation, PDF extraction.",
    "owns": [
        "the canonical record models and the work_id key chain",
        "text normalisation and deterministic hashing",
        "PDF-to-text extraction (no library state, no network)",
    ],
    "depends_on": [],
    "cli": [],
    "mcp": [],
}

# The canonical sequences. Each step names the command so the agent does not choose.
#
# Every step carries a `kind`: "command" steps hold an executable `cmd`, "human" steps
# hold a `do` describing work only the agent can perform. The distinction is enforced by
# tests/test_contract.py, because a machine consumer that walks every step and runs it
# would otherwise try to execute a sentence of English — which is exactly what the two
# prose steps used to look like when they sat in a `cmd` field.
WORKFLOWS: dict[str, dict[str, Any]] = {
    "answer-a-question-about-a-topic": {
        "when": "The user asks a question that papers in the corpus might answer.",
        "steps": [
            {"n": 1, "kind": "command", "cmd": "ccb ask \"<question>\" -n 5",
             "why": "Returns page-anchored passages from stored full text, not prose."},
            {"n": 2, "kind": "command", "cmd": "ccb get <work_id> --with-pdf",
             "why": "Only for works listed under 'skipped' that have no stored text yet."},
            {"n": 3, "kind": "human", "do": "compose the answer from the returned passages",
             "why": "Cite the anchors. If grounded is false, say the corpus does not cover it."},
        ],
        "notes": [
            "Never answer from memory when grounded is false — report the gap instead.",
            "Ranking is deterministic, so the same question yields the same citations.",
        ],
    },
    "find-then-read-a-topic": {
        "when": "The user asks about a topic and you need papers, PDFs or full text.",
        "steps": [
            {"n": 1, "kind": "command", "cmd": "ccb find \"<topic>\" -n 10",
             "why": "Hits the local library first; only misses go to channels. JSON is the "
                    "default output, so there is no --json flag to add."},
            {"n": 2, "kind": "command", "cmd": "ccb get <work_id> --with-pdf",
             "why": "Fetches only what is missing (metadata and/or text) and records it."},
            {"n": 3, "kind": "command", "cmd": "ccb open <work_id>",
             "why": "Reads local full text with zero network calls."},
        ],
        "notes": [
            "Step 2 is idempotent: re-running it on a complete record costs nothing.",
            "If a channel reports itself gated or missing a key, say so in the answer.",
        ],
    },
    "resolve-a-known-paper": {
        "when": "The user gives a DOI, arXiv id, OpenReview id, PMID, dblp key or title.",
        "steps": [
            {"n": 1, "kind": "command", "cmd": "ccb get <identifier> --with-pdf",
             "why": "Resolves locally first, then via channels; creates the record if new."},
        ],
        "notes": ["Any identifier form is accepted; the tool normalises it."],
    },
    "build-a-bibliography": {
        "when": "The user needs citations for a manuscript.",
        "steps": [
            {"n": 1, "kind": "command", "cmd": "ccb find \"<topic>\"",
             "why": "Populate the library."},
            {"n": 2, "kind": "command", "cmd": "ccb get <work_id> --with-pdf",
             "why": "Ensure metadata is complete."},
            {"n": 3, "kind": "command", "cmd": "ccb cite <work_id>",
             "why": "Inspect one entry and which source supplied each field."},
            {"n": 4, "kind": "command", "cmd": "ccb export --format bibtex",
             "why": "Emit entries with provenance intact. The format is a flag value, not "
                    "a flag of its own."},
        ],
        "notes": [
            "Fields with no source are omitted rather than invented — never fabricate a "
            "volume, page range or DOI.",
            "`unavailable_fields` in `ccb cite` tells you which fields no source provided.",
        ],
    },
    "re-verify-a-library": {
        "when": "The user asks whether stored papers are still valid, or a retraction is suspected.",
        "steps": [
            {"n": 1, "kind": "command", "cmd": "ccb check --all",
             "why": "Re-queries only the decisive endpoints."},
            {"n": 2, "kind": "command", "cmd": "ccb library report",
             "why": "Shows what changed and what is unknown."},
        ],
        "notes": ["Absence of a retraction notice is reported as 'not found in the sources "
                  "checked', never as 'not retracted'."],
    },
    "recover-from-suspected-damage": {
        "when": "Something looks wrong: a work is missing, a query returns odd results, or a "
                "previous run was interrupted.",
        "steps": [
            {"n": 1, "kind": "command", "cmd": "ccb doctor", "why": "Full consistency report."},
            {"n": 2, "kind": "command", "cmd": "ccb repair", "why": "Rebuilds every derived artefact."},
        ],
        "notes": ["Repair never deletes or rewrites works/*.json; the worst case is a rebuild."],
    },
    "generate-a-research-topic": {
        "when": "The user names a direction and wants one topic worth doing, with evidence.",
        "steps": [
            {"n": 1, "kind": "command", "cmd": "ccb topics survey \"<direction>\"",
             "why": "Maps the corpus for that direction, and tops it up from channels when "
                    "it is too thin to mine. Reports what it added."},
            {"n": 2, "kind": "command", "cmd": "ccb topics gaps <survey_id>",
             "why": "Returns gap evidence with work_id + page anchors: self-declared "
                    "limitations, future-work sentences, and empty cells in the "
                    "method x task x dataset grid. Never prose."},
            {"n": 3, "kind": "command", "cmd": "ccb topics candidates <survey_id>",
             "why": "Applies the novelty operators to that evidence, runs the novelty "
                    "self-check, and ranks what survives."},
            {"n": 4, "kind": "command", "cmd": "ccb topics draft <candidate_id>",
             "why": "Commits to exactly one topic and returns a section skeleton in which "
                    "every claim carries its anchor. This is where one-at-a-time binds."},
            {"n": 5, "kind": "human", "do": "compose the topic text from the returned anchors",
             "why": "The tool does not write prose; you do. Cite work_id + page per claim, "
                    "exactly as `ask` requires."},
            {"n": 6, "kind": "command", "cmd": "ccb topics rate <topic_id>",
             "why": "CCF upper bound, band, per-rule basis and confidence — each input "
                    "recomputable, so the estimate can be argued with."},
            {"n": 7, "kind": "command", "cmd": "ccb topics save <topic_id>",
             "why": "Stores the structured record and exports the Markdown draft."},
        ],
        "notes": [
            "Never invent a citation. Every reference in the draft must come from the "
            "corpus, and `topics draft` names exactly which works are eligible.",
            "If `gaps` reports insufficient evidence, say so and stop. Do not lower the "
            "bar in order to produce something.",
            "The rating is an estimate with stated reasoning; present it as one.",
            "One topic per call. `topics list` shows what has already been mined.",
        ],
    },
}

# The only two kinds a workflow step may have. `command` steps are executable and are
# verified as such by tests/test_contract.py; `human` steps are work the tool cannot do.
STEP_KINDS: tuple[str, ...] = ("command", "human")

# Where the agent should look first. Ordering is the recommendation, not a menu.
ROUTING_HINTS: dict[str, str] = {
    "identify_a_cs_conference_paper": "openreview, then dblp (when reachable), then openalex",
    "identify_a_journal_article": "crossref (publisher of record), then openalex",
    "find_a_preprint_or_latex": "arxiv",
    "locate_legal_open_access_pdf": "openalex oa locations, then unpaywall, then arxiv",
    "broad_topic_discovery": "openalex and crossref for ranking; arxiv as an identifier and "
                             "full-text source only, because its relevance ranking is loose",
    "biomedicine": "europepmc, then pubmed",
    "anything_needing_a_doi": "crossref",
    "mine_a_research_topic": "the topics module reads the local corpus only; run "
                             "`ccb topics survey` first so the direction has enough stored "
                             "full text to mine, then follow its step order",
}

OUTPUT_CONVENTIONS: list[str] = [
    "All commands print JSON by default; --pretty is for humans only.",
    "Errors go to stderr as JSON with an 'error' key; stdout stays parseable.",
    "--offline makes a command fail rather than reach the network.",
    "Every record carries its field sources; quote them when a field matters.",
    "work_id is stable; hand it back verbatim in later calls.",
]


def contract() -> dict[str, Any]:
    """The full machine-readable contract."""
    return {
        "tool": "ccb",
        "purpose": (
            "Three modules over one shared floor. `search` obtains a paper from any legal "
            "source; `library` keeps it in a durable local corpus so nothing is ever "
            "searched, downloaded or parsed twice; `topics` mines that corpus for one "
            "research topic worth doing, with its evidence. Every face — CLI, MCP and "
            "Agent Skill — is a thin adapter over the same core, so they cannot disagree "
            "about identity, dedup policy, or what counts as a legal source."
        ),
        "modules": [CORE, *MODULES],
        "invariants": INVARIANTS,
        "workflows": WORKFLOWS,
        "routing": ROUTING_HINTS,
        "output": OUTPUT_CONVENTIONS,
        # Per-command top-level payload keys, keyed by CLI path. Declared so a consumer
        # never has to guess the shape of a response (or read the handler to learn it).
        "payload_shapes": {
            path: list(keys) for path, keys in sorted(ops.PAYLOAD_KEYS.items())
        },
    }


def contract_text() -> str:
    """Compact human/agent-readable rendering used by `ccb contract`."""
    lines = [
        "ccb — operating contract",
        "",
        "MODULES (one shared floor; a module may import only what it depends on)",
    ]
    for mod in [CORE, *MODULES]:
        deps = ", ".join(mod["depends_on"]) or "nothing"
        lines.append(f"  {mod['name']} ({mod['package']}) — {mod['role']}")
        lines.append(f"      depends on: {deps}")
        for owned in mod["owns"]:
            lines.append(f"      owns: {owned}")
        if mod["cli"]:
            lines.append(f"      cli: {', '.join(mod['cli'])}")
        if mod["mcp"]:
            lines.append(f"      mcp: {', '.join(mod['mcp'])}")
        lines.append("")
    lines.append("INVARIANTS (the program enforces these; do not work around them)")
    for inv in INVARIANTS:
        lines.append(f"  [{inv['id']}] {inv['rule']}")
        lines.append(f"      why: {inv['why']}")
    lines.append("")
    lines.append("WORKFLOWS")
    for name, wf in WORKFLOWS.items():
        lines.append(f"  {name} — {wf['when']}")
        for s in wf["steps"]:
            if s.get("kind") == "command":
                what = s.get("cmd", "")
            else:
                what = f"(you) {s.get('do', '')}"
            lines.append(f"      {s['n']}. {what}")
            lines.append(f"         {s['why']}")
        for note in wf.get("notes", []):
            lines.append(f"      note: {note}")
        lines.append("")
    lines.append("ROUTING (which channel for which job)")
    for job, hint in ROUTING_HINTS.items():
        lines.append(f"  {job}: {hint}")
    lines.append("")
    lines.append("OUTPUT")
    for conv in OUTPUT_CONVENTIONS:
        lines.append(f"  - {conv}")
    return "\n".join(lines)


def ordered_steps(workflow: str) -> list[dict[str, Any]]:
    wf = WORKFLOWS.get(workflow)
    return list(wf["steps"]) if wf else []
