"""The self-describing contract.

This module exists for one reason: an agent driving this tool will eventually skip a
step, reorder steps, or invent a step. The tool therefore states its own rules and
correct sequences in machine-readable form, and every command can return them.

The contract is the interface, not documentation prose that can drift away from the
code: the CLI, the Agent Skill and the MCP surface all read it from here.
"""

from __future__ import annotations

from typing import Any

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
        "rule": "Credentials are read from the environment and redacted at write time. Never "
                "print, log or pass a key value.",
        "why": "Some APIs authenticate by query string, so a URL can itself be a secret.",
    },
    {
        "id": "report-failures",
        "rule": "A channel that is gated, rate-limited or unavailable must be reported by name "
                "with a reason; never silently return an empty result.",
        "why": "'No results' and 'could not look' are different facts with different responses.",
    },
]

# The canonical sequences. Each step names the command so the agent does not choose.
WORKFLOWS: dict[str, dict[str, Any]] = {
    "answer-a-question-about-a-topic": {
        "when": "The user asks a question that papers in the corpus might answer.",
        "steps": [
            {"n": 1, "cmd": "lit ask \"<question>\" -n 5",
             "why": "Returns page-anchored passages from stored full text, not prose."},
            {"n": 2, "cmd": "lit get <work_id> --with-pdf",
             "why": "Only for works listed under 'skipped' that have no stored text yet."},
            {"n": 3, "cmd": "compose the answer from the returned passages",
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
            {"n": 1, "cmd": "lit find \"<topic>\" --json",
             "why": "Hits the local library first; only misses go to channels."},
            {"n": 2, "cmd": "lit get <work_id> --with-pdf",
             "why": "Fetches only what is missing (metadata and/or text) and records it."},
            {"n": 3, "cmd": "lit open <work_id>",
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
            {"n": 1, "cmd": "lit get <identifier> --with-pdf",
             "why": "Resolves locally first, then via channels; creates the record if new."},
        ],
        "notes": ["Any identifier form is accepted; the tool normalises it."],
    },
    "build-a-bibliography": {
        "when": "The user needs citations for a manuscript.",
        "steps": [
            {"n": 1, "cmd": "lit find \"<topic>\"", "why": "Populate the library."},
            {"n": 2, "cmd": "lit get <work_id> --with-pdf", "why": "Ensure metadata is complete."},
            {"n": 3, "cmd": "lit cite <work_id>",
             "why": "Inspect one entry and which source supplied each field."},
            {"n": 4, "cmd": "lit export --bibtex", "why": "Emit entries with provenance intact."},
        ],
        "notes": [
            "Fields with no source are omitted rather than invented — never fabricate a "
            "volume, page range or DOI.",
            "`unavailable_fields` in `lit cite` tells you which fields no source provided.",
        ],
    },
    "re-verify-a-library": {
        "when": "The user asks whether stored papers are still valid, or a retraction is suspected.",
        "steps": [
            {"n": 1, "cmd": "lit check --all", "why": "Re-queries only the decisive endpoints."},
            {"n": 2, "cmd": "lit library report", "why": "Shows what changed and what is unknown."},
        ],
        "notes": ["Absence of a retraction notice is reported as 'not found in the sources "
                  "checked', never as 'not retracted'."],
    },
    "recover-from-suspected-damage": {
        "when": "Something looks wrong: a work is missing, a query returns odd results, or a "
                "previous run was interrupted.",
        "steps": [
            {"n": 1, "cmd": "lit doctor", "why": "Full consistency report."},
            {"n": 2, "cmd": "lit repair", "why": "Rebuilds every derived artefact."},
        ],
        "notes": ["Repair never deletes or rewrites works/*.json; the worst case is a rebuild."],
    },
}

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
        "tool": "lit",
        "purpose": (
            "Aggregate every paper search/download channel behind one entry point, and keep "
            "a durable local library so the same paper is never searched, downloaded and "
            "parsed twice."
        ),
        "invariants": INVARIANTS,
        "workflows": WORKFLOWS,
        "routing": ROUTING_HINTS,
        "output": OUTPUT_CONVENTIONS,
    }


def contract_text() -> str:
    """Compact human/agent-readable rendering used by `lit contract`."""
    lines = [
        "lit — operating contract",
        "",
        "INVARIANTS (the program enforces these; do not work around them)",
    ]
    for inv in INVARIANTS:
        lines.append(f"  [{inv['id']}] {inv['rule']}")
        lines.append(f"      why: {inv['why']}")
    lines.append("")
    lines.append("WORKFLOWS")
    for name, wf in WORKFLOWS.items():
        lines.append(f"  {name} — {wf['when']}")
        for s in wf["steps"]:
            lines.append(f"      {s['n']}. {s['cmd']}")
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
