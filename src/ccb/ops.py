"""Every operation, declared once, for all three faces.

The tool has three faces — CLI, MCP server and the contract it publishes — and each one
needs the same list of operations with the same parameters. Keeping three hand-written
lists in step cost five or six edits per new operation, and the two ways they could
disagree were both silent: an MCP tool listed without a handler, or a contract naming a
flag that does not exist (both happened; see tests/test_contract.py and tests/test_ops.py).

So the list lives here and the faces are derived from it:

* ``cli/_parser.py`` builds its argparse subparsers from these params,
* ``mcp_server.py`` builds its ``inputSchema`` from the same params,
* ``contract.py``  derives its per-module ``cli``/``mcp`` name lists.

A param may be reachable from one face only — ``cli_only`` for conveniences with no tool
equivalent, ``mcp_only`` for tool-specific switches — and the names may differ between the
faces (``--source`` on the CLI is ``sources`` over MCP). Both are declared rather than
implied, which is what lets a test hold the faces to each other.

Standard library only: this module is imported by the entry layer, not by the modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Param:
    """One input, with the spelling each face uses for it."""

    name: str                      # canonical name: MCP schema key and argparse dest
    kind: str = "str"              # str | int | flag | csv
    cli: str = ""                  # "|"-joined CLI option strings; "" means positional
    dest: str = ""                 # argparse dest, when it differs from `name`
    help: str = ""
    default: Any = None
    required: bool = False
    choices: tuple[str, ...] = ()
    cli_only: bool = False         # not exposed over MCP
    mcp_only: bool = False         # not accepted on the CLI

    @property
    def argparse_dest(self) -> str:
        return self.dest or self.name


@dataclass(frozen=True)
class Operation:
    """One thing the tool can do."""

    name: str                      # CLI subcommand name (last segment for grouped ops)
    summary: str = ""
    handler: str = ""              # CLI handler function name in cli/_handlers.py
    params: tuple[Param, ...] = ()
    group: str = ""                # "" = top level; otherwise a parent subcommand
    module: str = ""               # core | library | search | topics | "" (entry layer)
    mcp: str = ""                  # MCP tool name; "" = not exposed over MCP
    records_key: tuple[str, ...] = ()   # payload keys holding record lists, for --pretty

    @property
    def mcp_handler(self) -> str:
        """The ``_tool_*`` method name this operation dispatches to."""
        return self.mcp.removeprefix("ccb_") if self.mcp else ""

    @property
    def path(self) -> str:
        return f"{self.group} {self.name}".strip()


OPERATIONS: tuple[Operation, ...] = (

    Operation("channels", group="", module="search", mcp="ccb_channels",
              handler="cmd_channels",
              summary='list channels, availability and missing credentials',
              params=(
        Param(name="name", kind="str", cli="", help='detail for one channel', cli_only=True),
              ),
              ),
    Operation("contract", group="", module="", mcp="ccb_contract",
              handler="cmd_contract",
              summary='the operating rules and canonical step order',
              ),
    Operation("install-skill", group="", module="", mcp="",
              handler="cmd_install_skill",
              summary='copy the bundled Agent Skill into a project (or --global)',
              params=(
        Param(name="global", kind="flag", cli="--global", dest="global_skill",
              default=False, help='install into ~/.dsh/skills instead of the current project'),
        Param(name="force", kind="flag", cli="--force", default=False,
              help='overwrite an existing installation'),
              )),
    Operation("doctor", group="", module="library", mcp="",
              handler="cmd_doctor",
              summary='consistency report for the library',
              params=(
        Param(name="repair", kind="flag", cli="--repair", default=False, help='rebuild derived artefacts'),
              ),
              ),
    Operation("repair", group="", module="library", mcp="",
              handler="cmd_repair",
              summary='force a full rebuild of derived artefacts',
              params=(
        Param(name="reidentify", kind="flag", cli="--reidentify", default=False,
              help='also re-derive every work id from its normalized identifiers'),
        Param(name="dry_run", kind="flag", cli="--dry-run", default=False,
              help='with --reidentify: report what would move and change nothing'),
              ),
              ),
    Operation("find", group="", module="search", mcp="ccb_find",
              handler="cmd_find",
              summary='search: local library first, then channels',
              records_key=('local_hits', 'fetched'),
              params=(
        Param(name="query", kind="str", cli="", required=True),
        Param(name="limit", kind="int", cli="-n|--limit", default=10),
        Param(name="sources", dest="source", kind="str", cli="-s|--source", help='channel selector: auto | all | a,b,c'),
        Param(name="year_from", kind="int", cli="--year-from"),
        Param(name="year_to", kind="int", cli="--year-to"),
        Param(name="no_local", kind="flag", cli="--no-local", default=False, help='skip the local pass', cli_only=True),
        Param(name="no_ingest", kind="flag", cli="--no-ingest", default=False, help='do not store channel results', cli_only=True),
        Param(name="min_local", kind="int", cli="--min-local", default=0, help='only query channels when fewer than N local hits exist', cli_only=True),
        Param(name="compact", kind="flag", cli="--compact", default=False, help='trim records to key fields', cli_only=True),
              ),
              ),
    Operation("get", group="", module="search", mcp="ccb_get",
              handler="cmd_get",
              summary='acquire one paper: local first, then channels',
              params=(
        Param(name="identifier", kind="str", cli="", required=True, help='DOI, arXiv id, OpenReview id, dblp key, PMID, URL, work_id'),
        Param(name="with_pdf", kind="flag", cli="--with-pdf", default=False),
        Param(name="extract", kind="flag", cli="--extract", default=False, help='extract text after downloading', cli_only=True),
        Param(name="refresh", kind="flag", cli="--refresh", default=False, help='re-query channels even if local'),
        Param(name="source", kind="str", cli="-s|--source", help='channel selector', cli_only=True),
        Param(name="full", kind="flag", cli="--full", default=False, help='include the full record, not a summary', cli_only=True),
              ),
              ),
    Operation("ask", group="", module="library", mcp="ccb_ask",
              handler="cmd_ask",
              summary='retrieve passages that answer a question, with page-anchored citations',
              params=(
        Param(name="query", kind="str", cli="", required=True),
        Param(name="limit", kind="int", cli="-n|--limit", default=5, help='passages to return'),
        Param(name="work_ids", dest="ids", kind="csv", cli="--ids", help='comma-separated work ids to search (default: whole library)'),
        Param(name="section", kind="str", cli="--section",
              help='only passages under a matching section heading (e.g. methods)'),
        Param(name="max_per_work", kind="int", cli="--max-per-work", default=2, help='diversity guard so one long paper cannot fill the results', cli_only=True),
        Param(name="quotes_only", kind="flag", cli="--quotes-only", default=False, help='omit the passage text, keep the anchors and scores', cli_only=True),
              ),
              ),
    Operation("index", group="", module="library", mcp="",
              handler="cmd_index",
              summary='build/refresh the passage index for stored full texts',
              params=(
        Param(name="ids", kind="str", cli="--ids", help='comma-separated work ids (default: whole library)'),
              ),
              ),
    Operation("cite", group="", module="library", mcp="ccb_cite",
              handler="cmd_cite",
              summary='citation for one work, with field provenance',
              params=(
        Param(name="identifier", kind="str", cli="", required=True),
        Param(name="format", kind="str", cli="--format", default='bibtex'),
        Param(name="key_style", kind="str", cli="--key-style", default='authorYear', cli_only=True),
              ),
              ),
    Operation("open", group="", module="library", mcp="ccb_open",
              handler="cmd_open",
              summary='read local full text (never touches the network)',
              params=(
        Param(name="identifier", kind="str", cli="", required=True),
        Param(name="head", kind="int", cli="--head", default=0, help='only the first N characters'),
              ),
              ),
    Operation("show", group="", module="library", mcp="",
              handler="cmd_show",
              summary='show one stored record with its claim provenance',
              params=(
        Param(name="identifier", kind="str", cli="", required=True),
        Param(name="raw", kind="flag", cli="--raw", default=False, help='raw stored JSON'),
              ),
              ),
    Operation("search-local", group="", module="library", mcp="",
              handler="cmd_search_local",
              summary='search only the local library',
              records_key=('hits',),
              params=(
        Param(name="query", kind="str", cli=""),
        Param(name="limit", kind="int", cli="-n|--limit", default=25),
        Param(name="year_from", kind="int", cli="--year-from"),
        Param(name="year_to", kind="int", cli="--year-to"),
        Param(name="venue", kind="str", cli="--venue"),
        Param(name="author", kind="str", cli="--author"),
        Param(name="with_pdf", kind="flag", cli="--with-pdf", default=False),
              ),
              ),
    Operation("stats", group="library", module="library", mcp="ccb_stats",
              handler="cmd_library",
              summary='corpus state, including pending duplicate candidates',
              params=(
        Param(name="limit", kind="int", cli="-n|--limit", default=0, cli_only=True),
              ),
              ),
    Operation("report", group="library", module="library", mcp="",
              handler="cmd_library",
              summary='stats plus pending merges and recent ledger events',
              params=(
        Param(name="limit", kind="int", cli="-n|--limit", default=0, cli_only=True),
              ),
              ),
    Operation("list", group="library", module="library", mcp="",
              handler="cmd_library",
              summary='every stored work, newest first',
              records_key=('works',),
              params=(
        Param(name="limit", kind="int", cli="-n|--limit", default=0, cli_only=True),
              ),
              ),
    Operation("merges", group="library", module="library", mcp="",
              handler="cmd_library",
              summary='merges awaiting an explicit decision',
              records_key=('pending',),
              params=(
        Param(name="limit", kind="int", cli="-n|--limit", default=0, cli_only=True),
              ),
              ),
    Operation("check", group="", module="search", mcp="",
              handler="cmd_check",
              summary='re-verify stored records against the sources',
              params=(
        Param(name="ids", kind="str", cli="", help='comma-separated work ids'),
        Param(name="all", kind="flag", cli="--all", default=False),
        Param(name="limit", kind="int", cli="-n|--limit", default=0),
              ),
              ),
    Operation("check-files", group="", module="search", mcp="",
              handler="cmd_check_files",
              summary='verify stored PDFs against recorded hashes',
              ),
    Operation("export", group="", module="library", mcp="ccb_export",
              handler="cmd_export",
              summary='export citations (bibtex/ris/csl/text)',
              params=(
        Param(name="format", kind="str", cli="--format", default='bibtex'),
        Param(name="key_style", kind="str", cli="--key-style", default='authorYear', cli_only=True),
        Param(name="work_ids", dest="ids", kind="csv", cli="--ids", help='comma-separated work ids (default: whole library)'),
        Param(name="query", kind="str", cli="--query", help='substring filter over title/abstract'),
        Param(name="out", kind="str", cli="-o|--out", help='write to a file instead of stdout', cli_only=True),
        Param(name="raw", kind="flag", cli="--raw", default=False, help='print the citation text itself, not JSON (for redirection)', cli_only=True),
              ),
              ),
    Operation("add-file", group="", module="library", mcp="",
              handler="cmd_add_file",
              summary='add a PDF you already have into the library',
              params=(
        Param(name="file", kind="str", cli="", required=True),
        Param(name="title", kind="str", cli="--title"),
        Param(name="authors", kind="str", cli="--authors", help='semicolon-separated'),
        Param(name="year", kind="int", cli="--year"),
        Param(name="venue", kind="str", cli="--venue"),
        Param(name="doi", kind="str", cli="--doi"),
        Param(name="arxiv", kind="str", cli="--arxiv"),
        Param(name="openreview", kind="str", cli="--openreview"),
        Param(name="url", kind="str", cli="--url"),
        Param(name="extract", kind="flag", cli="--extract", default=False),
        Param(name="allow_non_pdf", kind="flag", cli="--allow-non-pdf", default=False),
              ),
              ),
    Operation("extract", group="", module="library", mcp="",
              handler="cmd_extract",
              summary='extract text from a stored PDF',
              params=(
        Param(name="identifier", kind="str", cli="", required=True),
        Param(name="engine", kind="str", cli="--engine", default=''),
              ),
              ),
    Operation("merge", group="", module="library", mcp="",
              handler="cmd_merge",
              summary='confirm a merge of two works',
              params=(
        Param(name="keep", kind="str", cli="", required=True),
        Param(name="drop", kind="str", cli="", required=True),
              ),
              ),
    Operation("evidence", group="", module="library", mcp="",
              handler="cmd_evidence",
              summary='inspect raw response snapshots',
              params=(
        Param(name="id", kind="str", cli="--id", help='render one snapshot'),
        Param(name="limit", kind="int", cli="-n|--limit", default=0),
              ),
              ),
    Operation("ledger", group="", module="library", mcp="",
              handler="cmd_ledger",
              summary='read the append-only audit trail',
              params=(
        Param(name="limit", kind="int", cli="-n|--limit", default=50),
        Param(name="event", kind="str", cli="--event"),
        Param(name="compact", kind="int", cli="--compact", default=0, cli_only=True,
              help='maintenance: keep only the newest N events, archiving the rest'),
              ),
              ),
    Operation("reindex", group="", module="library", mcp="",
              handler="cmd_reindex",
              summary='rebuild the derived index (rarely needed)',
              ),
    Operation("survey", group="topics", module="topics", mcp="ccb_topics_survey",
              handler="cmd_topics",
              summary='map the corpus for a direction, topping it up if thin',
              params=(
        Param(name="query", kind="str", cli="", required=True, help='the direction, e.g. "graph neural networks for molecules"'),
        Param(name="min_works", kind="int", cli="--min-works", default=20, help='top up from channels below this many works (default 20)'),
        Param(name="min_fulltext", kind="int", cli="--min-fulltext", default=5, help='aim for this many works with stored full text (default 5)'),
        Param(name="year_from", kind="int", cli="--year-from"),
        Param(name="year_to", kind="int", cli="--year-to"),
        Param(name="limit", kind="int", cli="-n|--limit", default=200, help='max works to include'),
        Param(name="top_terms", kind="int", cli="--top-terms", default=40),
        Param(name="max_n", kind="int", cli="--max-n", default=2, help='longest term phrase to extract (1-3)'),
        Param(name="offline", kind="flag", mcp_only=True, help="refuse to top up from the network"),
              ),
              ),
    Operation("gaps", group="topics", module="topics", mcp="ccb_topics_gaps",
              handler="cmd_topics",
              summary='gap evidence for a survey: quotes, statistics, kinds',
              params=(
        Param(name="survey_id", kind="str", cli="", required=True),
        Param(name="limit", kind="int", cli="-n|--limit", default=60, help='max declared gaps'),
        Param(name="max_per_work", kind="int", cli="--max-per-work", default=3),
              ),
              ),
    Operation("candidates", group="topics", module="topics", mcp="ccb_topics_candidates",
              handler="cmd_topics",
              summary='ranked (evidence x operator) topic candidates',
              params=(
        Param(name="survey_id", kind="str", cli="", required=True),
        Param(name="limit", kind="int", cli="-n|--limit", default=25),
        Param(name="per_kind", kind="int", cli="--per-kind", default=15, help='how many pieces of each evidence kind to consider'),
        Param(name="include_mined", kind="flag", cli="--include-mined", default=False, help='also show combinations already committed'),
        Param(name="no_self_check", kind="flag", cli="--no-self-check", default=False, help='skip the local novelty coverage check'),
              ),
              ),
    Operation("draft", group="topics", module="topics", mcp="ccb_topics_draft",
              handler="cmd_topics",
              summary='commit to one candidate; returns the section skeleton',
              params=(
        Param(name="candidate_id", kind="str", cli="", required=True),
              ),
              ),
    Operation("rate", group="topics", module="topics", mcp="ccb_topics_rate",
              handler="cmd_topics",
              summary='CCF estimate: upper bound, band, basis, risks',
              params=(
        Param(name="topic_id", kind="str", cli="", required=True),
        Param(name="venue", kind="str", cli="--venue", help='target venue to check the estimate against'),
              ),
              ),
    Operation("save", group="topics", module="topics", mcp="ccb_topics_save",
              handler="cmd_topics",
              summary='commit a topic and export its Markdown draft',
              params=(
        Param(name="topic_id", kind="str", cli="", required=True),
              ),
              ),
    Operation("list", group="topics", module="topics", mcp="ccb_topics_list",
              handler="cmd_topics",
              summary='topics already mined, and what they consumed',
              records_key=('topics',),
              params=(
        Param(name="limit", kind="int", cli="-n|--limit", default=0),
              ),
              ),
    Operation("show", group="topics", module="topics", mcp="",
              handler="cmd_topics",
              summary='one stored topic, with its anchors and references',
              params=(
        Param(name="topic_id", kind="str", cli="", required=True),
        Param(name="markdown", kind="flag", cli="--markdown", default=False, help='emit the rendered Markdown'),
              ),
              ),
    Operation("venues", group="topics", module="topics", mcp="",
              handler="cmd_topics",
              summary='the CCF catalogue: look a venue up, or verify it',
              params=(
        Param(name="query", kind="str", cli="", help='substring to search for'),
        Param(name="limit", kind="int", cli="-n|--limit", default=20),
        Param(name="verify", kind="flag", cli="--verify", default=False, help='self-check the loaded catalogue'),
              ),
              ),
    Operation("operators", group="topics", module="topics", mcp="",
              handler="cmd_topics",
              summary='the novelty operators and their difficulty scale',
              ),
)


BY_NAME: dict[str, Operation] = {op.name: op for op in OPERATIONS if not op.group}
BY_PATH: dict[str, Operation] = {op.path: op for op in OPERATIONS}
BY_MCP: dict[str, Operation] = {op.mcp: op for op in OPERATIONS if op.mcp}

# The parent subcommands: what they are called, and the attribute their handler reads.
GROUP_INFO: dict[str, dict[str, str]] = {
    "library": {
        "help": "library-level views",
        "dest": "action",
    },
    "topics": {
        "help": "mine the corpus for one research topic worth doing (module three)",
        "dest": "topics_action",
        "description": (
            "Survey a direction in the local corpus, extract the gaps it documents, "
            "apply novelty operators to that evidence, and build one topic at a time. "
            "The tool returns anchored evidence and a section skeleton; the agent "
            "writes the prose."
        ),
    },
}


def groups() -> list[str]:
    """Parent subcommands, in declaration order."""
    seen: list[str] = []
    for op in OPERATIONS:
        if op.group and op.group not in seen:
            seen.append(op.group)
    return seen


def in_group(group: str) -> list[Operation]:
    return [op for op in OPERATIONS if op.group == group]


def cli_names(module: str) -> list[str]:
    """The contract's `cli` list for a module: top-level commands plus its groups."""
    names = [op.name for op in OPERATIONS if op.module == module and not op.group]
    names += [g for g in groups() if any(op.module == module for op in in_group(g))]
    return names


def mcp_names(module: str) -> list[str]:
    return [op.mcp for op in OPERATIONS if op.module == module and op.mcp]


@dataclass(frozen=True)
class Prompt:
    """One MCP prompt template: a named, reusable agent workflow.

    Prompts are the third MCP surface (beside tools and resources): a client can offer
    them as one-click starting points. The templates here are the canonical sequences
    from SKILL.md, written so an agent that follows them cannot skip the rules — each
    step names its command, and the wording rules are baked into the text.
    """

    name: str
    description: str
    arguments: tuple[Param, ...] = ()
    template: str = ""


PROMPTS: tuple[Prompt, ...] = (
    Prompt(
        name="ccb-literature-review",
        description=(
            "Run the canonical literature flow for one topic: find, acquire, read and "
            "report with page anchors. Six steps, each naming its command."
        ),
        arguments=(
            Param(name="topic", required=True,
                  help="the research direction, e.g. 'NIC offloading on SmartNICs'"),
            Param(name="limit", kind="int", default=10,
                  help="papers per search"),
        ),
        template=(
            "Build a short literature review on: {topic}\n\n"
            "Follow this exact order and say which step you are on:\n"
            "1. `ccb find \"{topic}\" -n {limit}` - the local library is consulted "
            "first; only a miss goes to the network.\n"
            "2. For the 3-5 most relevant works: `ccb get <work_id> --with-pdf` "
            "(idempotent - re-running a complete record costs nothing).\n"
            "3. `ccb ask \"<question>\"` to pull page-anchored passages instead of "
            "re-reading whole PDFs.\n"
            "4. Compose the review ONLY from returned passages, citing work_id + page "
            "for every claim. If `outcome` is \"not-covered\" for a sub-question, say "
            "the corpus does not cover it - never fill the gap from memory.\n"
            "5. `ccb export --format bibtex` for the works you cited.\n\n"
            "Exit code 4 means partial: some channels failed. Report which, by name, "
            "and do not retry them in a loop."
        ),
    ),
    Prompt(
        name="ccb-compare-papers",
        description=(
            "Compare two stored papers along problem, method, data, findings and "
            "limitations, with an anchor for every comparative statement."
        ),
        arguments=(
            Param(name="work_id_a", required=True, help="first work_id"),
            Param(name="work_id_b", required=True, help="second work_id"),
        ),
        template=(
            "Compare two papers from the local library: {work_id_a} and {work_id_b}.\n\n"
            "1. `ccb open {work_id_a} --head 20000` and the same for {work_id_b} - "
            "reading locally never touches the network.\n"
            "2. `ccb show {work_id_a}` and `{work_id_b}` - check `conflicts` and "
            "`field_sources`; report where sources disagree instead of picking one.\n"
            "3. Compare along: problem, method, data, findings, limitations.\n"
            "4. Every comparative statement needs an anchor (work_id + page), either "
            "from the full text or from `ccb ask`.\n"
            "5. If either paper is not in the library, `ccb get <identifier> "
            "--with-pdf` first; if there is no legal full text, say so and compare the "
            "metadata honestly."
        ),
    ),
    Prompt(
        name="ccb-verify-claims",
        description=(
            "Check a written claim against the local corpus, part by part, with "
            "page-anchored passages."
        ),
        arguments=(
            Param(name="claim", required=True,
                  help="the claim to verify, one sentence"),
        ),
        template=(
            "Verify this claim against the local corpus: \"{claim}\"\n\n"
            "1. Break the claim into its checkable parts.\n"
            "2. `ccb ask \"<part>\"` for each part; use `--section` to narrow (a "
            "limitations statement lives in the discussion, a benchmark description in "
            "the methods).\n"
            "3. For each part report one of: SUPPORTED (cite work_id + page), "
            "CONTRADICTED (cite), NOT-COVERED.\n"
            "4. NOT-COVERED means the corpus does not cover it - never answer that "
            "part from memory.\n"
            "5. End with an overall verdict and the exact anchors a reader should check."
        ),
    ),
    Prompt(
        name="ccb-idea-review",
        description=(
            "Adversarial pre-commit review of a topic draft or idea: three fresh-eyes "
            "sub-agents attack it from reviewer / engineer / cold-water perspectives, "
            "then every finding is re-verified against the corpus before a verdict. "
            "Defends against single-session context contamination."
        ),
        arguments=(
            Param(name="draft", required=True,
                  help="the topic draft or idea text to review"),
            Param(name="topic_id", required=False,
                  help="a stored topic id from `ccb topics draft`, if one exists"),
        ),
        template=(
            "Adversarially review this topic draft or idea before any commitment:\n"
            "\"{draft}\"\n\n"
            "Run three stages in order; do not merge them.\n\n"
            "Stage 1 - fresh-eyes sub-review. The point is independence, not speed: "
            "spawn THREE sub-agents in parallel (at most 4 concurrent; a sub-agent "
            "never spawns further sub-agents). Each receives the draft text and "
            "corpus anchors ONLY - never this session's own reasoning. Dispatch "
            "shape for every sub-agent:\n"
            "  [task] attack the draft from ONE assigned perspective\n"
            "  [background] corpus anchors: run `ccb topics show {topic_id}` or "
            "`ccb ask` first, and paste the anchors\n"
            "  [boundary] judge only this draft; do not propose your own idea\n"
            "  [output] verdict (keep / revise / kill) + top 3 findings, each "
            "quoting the exact draft sentence it attacks\n"
            "  [forbidden] invented facts, papers or numbers; padding\n"
            "Perspectives: REVIEWER - is the novelty real? name the most dangerous "
            "neighbour (a real, citable work) and the exact difference. ENGINEER - "
            "what is the minimal runnable loop: hardware, data, cost, weeks. COLD "
            "WATER - which single experiment could kill this outright?\n\n"
            "Stage 2 - re-verify every finding yourself; the sub-agents advise, they "
            "do not judge. For each claim check its premise against the corpus first "
            "(`ccb ask`, `ccb cite`), then adopt, discount or reject it, quoting the "
            "text you checked. Label any attack you could not verify as SPECULATIVE. "
            "Novelty checks: not-found is not does-not-exist - say which queries you "
            "ran.\n\n"
            "Stage 3 - position with evidence, not vibes. `ccb topics rate {topic_id}` "
            "(or estimate against `ccb topics venues --verify`) for the CCF band, and "
            "state the CONTRIBUTION TYPE explicitly: a new failure mode, a relaxed "
            "assumption, a measurement instrument, a formal result, or a system. "
            "Adding a module to existing work is the weakest type - its ceiling is "
            "set by the type, not by how well it is sewn.\n\n"
            "Final output: one verdict per idea (keep / revise / kill), the ceiling "
            "estimate with its basis, a kill criterion (one number, frozen now), and "
            "the idea card's destination - the user's own research notes, not the "
            "library. Every judgement cites a text you actually read."
        ),
    ),
    Prompt(
        name="ccb-topic-stitch",
        description=(
            "Build a paper candidate by deliberate stitching: pick a base, pool "
            "modules, then write the And-But-Therefore story from verified gap "
            "anchors - with the honesty rules that keep stitching publishable "
            "(report all results, ceiling set by contribution type)."
        ),
        arguments=(
            Param(name="direction", required=True,
                  help="the research direction, e.g. 'cross-protocol encrypted "
                       "traffic classification'"),
        ),
        template=(
            "Build a paper candidate for \"{direction}\" by deliberate stitching - "
            "and be honest about what that is.\n\n"
            "1. Pick the base: from `ccb topics candidates` and stored records, "
            "prefer works with available code; note its venue and what it already "
            "claims.\n"
            "2. Build the module pool: 8-12 candidate modules from the methods of "
            "corpus records (attention, contrastive, domain adaptation, feature "
            "fusion, ...). `ccb topics operators` ranks them by difficulty; a "
            "homogeneous pool sews fast but reviewers have seen it all.\n"
            "3. Sew with the honest rule: most combinations fail (80% is normal) and "
            "a failure is a result, not an embarrassment. When something works only "
            "under condition X, write the boundary condition - that is a "
            "contribution, not a confession. Report everything: all seeds, all "
            "datasets, negative results.\n"
            "4. Ceiling check BEFORE writing: name the contribution type. If the "
            "honest answer is 'a module added or a setting swapped', target CCF-C / "
            "Q2 and write it that way - polishing cannot raise the ceiling; only the "
            "contribution type can.\n"
            "5. Story line, And-But-Therefore, every element anchored: And - what "
            "the corpus already shows (cite `ccb topics gaps` or record anchors). "
            "But - the conflict, which MUST come from verified gap anchors; "
            "inventing a conflict is fabrication. Therefore - the contribution, "
            "phrased as information gain for the reader.\n"
            "6. Three experiments minimum: head-to-head against the strongest "
            "baseline, ablation (remove each module), and an instance analysis of "
            "the boundary condition.\n\n"
            "Deliverable: a one-page candidate with the claim, the ABT story, the "
            "experiment grid, the cost estimate and the frozen kill criterion. The "
            "idea card goes to the user's research notes; the evidence stays in the "
            "library."
        ),
    ),
)


# --------------------------------------------------------------------------- #
# Output payload shapes
# --------------------------------------------------------------------------- #

# The top-level keys each command's stdout JSON carries, keyed by the operation's CLI
# path (`op.path or op.name`). Declared here, derived into `ccb contract`, and pinned
# by tests/test_cli.py — because the alternative is every consumer discovering the keys
# by trial and error, which is exactly what happened before this table existed.
#
# Where a payload varies by outcome (a partial exit carries `errors`/`warnings` that a
# clean run omits), the declaration is the union; the test asserts that a run never
# emits a key outside the declaration, and never misses one on success.
PAYLOAD_KEYS: dict[str, tuple[str, ...]] = {
    # -- library ------------------------------------------------------------ #
    "channels": ("channels", "credential_guidance", "credentials_missing",
                 "credentials_present", "note", "unavailable", "usable"),
    "contract": ("invariants", "modules", "output", "payload_shapes", "purpose",
                 "routing", "tool", "workflows"),
    "doctor": ("channels_unavailable", "channels_usable", "checked_at", "extractors",
               "index_ok", "library_root", "meta", "problems", "repaired",
               "works_on_disk"),
    "repair": ("checked_at", "dry_run", "failed", "index_ok", "library_root",
               "problems", "reidentified", "repaired", "sample", "works_checked",
               "works_indexed", "works_on_disk"),
    "find": ("channels_queried", "fetched", "ingested", "local_answered",
             "local_hits", "message", "query"),
    "get": ("actions", "errors", "message", "ok", "record", "source", "warnings",
            "work_id"),
    "ask": ("corpus", "grounded", "hits", "message", "note", "outcome", "query",
            "skipped"),
    "index": ("count", "indexed", "skipped"),
    "cite": ("citation", "format", "note", "provenance", "unavailable_fields",
             "work_id"),
    "open": ("chars", "text", "title", "total_chars", "truncated", "work_id"),
    "show": ("arxiv_id", "authors", "check_status", "claim_conflicts", "conflicts",
             "doi", "field_sources", "has_fulltext", "has_pdf", "ids",
             "manifestations", "manifestations_detail", "openreview_id", "pdf_path",
             "title", "venue", "work_id", "year"),
    "search-local": ("count", "hits", "query"),
    "library stats": ("evidence_snapshots", "index_present", "ledger_archived",
                      "ledger_events", "pdf_bytes", "pdf_mb", "pending_merges", "root",
                      "top_venues", "with_fulltext", "with_pdf", "works",
                      "works_with_conflicts", "year_range"),
    "library report": ("evidence_snapshots", "index_present", "ledger_archived",
                       "ledger_events", "pdf_bytes", "pdf_mb", "pending_merges",
                       "recent_events", "root", "top_venues", "with_fulltext",
                       "with_pdf", "works", "works_with_conflicts", "year_range"),
    "library list": ("count", "works"),
    "library merges": ("pending",),
    "check": ("at", "changed", "checked", "errors", "unchanged", "unverifiable"),
    "check-files": ("checked", "mismatch", "missing", "ok", "orphans"),
    "export": ("entries", "format", "text"),
    "add-file": ("action", "bytes", "extraction", "merge_candidates", "sha256",
                 "stored_path", "work_id"),
    "extract": ("chars", "engine", "error", "ok", "pages", "pages_indexed",
                "passages", "stored_path", "warnings", "work_id"),
    "merge": ("drop", "fields", "keep", "merged"),
    "evidence": ("count", "ids"),
    "ledger": ("count", "events"),
    "reindex": ("works",),
    "install-skill": ("files", "installed", "note"),
    # -- topics ------------------------------------------------------------- #
    "topics survey": ("catalog", "ccf", "corpus", "found_via", "message", "notes",
                      "query", "sufficient", "survey_id", "terms", "thresholds",
                      "top_authors", "venues", "window", "works", "years"),
    "topics gaps": ("coverage", "declared_gaps", "error", "gap_kinds", "message",
                    "query", "sparse_pairs", "survey_id", "usable"),
    "topics candidates": ("candidates", "error", "excluded_as_mined", "generated",
                          "message", "note", "query", "returned", "survey",
                          "survey_id", "weights"),
    "topics draft": ("candidate_id", "context", "corpus", "created_at", "dedup_keys",
                     "error", "evidence", "message", "next_steps", "operator",
                     "problem", "query", "references", "score", "score_basis",
                     "sections", "status", "survey_id", "title_hint", "topic_id"),
    "topics rate": ("basis", "computed_at", "confidence", "disclaimer",
                    "error", "estimated_ccf", "message", "risks", "steps_down",
                    "target_venue", "target_venue_ccf", "topic_id", "upper_bound"),
    "topics save": ("error", "markdown", "markdown_path", "message", "topic_id",
                    "warnings"),
    "topics list": ("count", "mined_keys", "note", "topics"),
    "topics show": ("candidate_id", "context", "corpus", "created_at", "dedup_keys",
                    "error", "evidence", "markdown_path", "message", "next_steps",
                    "operator", "problem", "query", "references", "score",
                    "score_basis", "sections", "status", "survey_id", "title_hint",
                    "topic_id"),
    "topics venues": ("catalog", "count", "note", "query", "venues"),
    "topics operators": ("difficulty_scale", "novelty_types", "operators"),
}


def payload_keys(path: str) -> tuple[str, ...]:
    """Declared top-level keys for one operation's stdout payload."""
    return PAYLOAD_KEYS.get(path, ())


def prompt_definitions() -> list[dict[str, Any]]:
    """The MCP `prompts/list` payload, derived from the declaration."""
    return [
        {
            "name": p.name,
            "description": p.description,
            "arguments": [
                {
                    "name": a.name,
                    "description": a.help,
                    "required": a.required,
                }
                for a in p.arguments
            ],
        }
        for p in PROMPTS
    ]


def render_prompt(name: str, args: dict[str, Any]) -> str:
    """Fill one prompt template. Raises KeyError for an unknown name."""
    for p in PROMPTS:
        if p.name == name:
            text = p.template
            for a in p.arguments:
                text = text.replace("{" + a.name + "}", str((args or {}).get(a.name, "")))
            return text
    raise KeyError(name)


# Long-form tool descriptions, shown to MCP clients. Kept here so a tool's name,
# its parameters and its description are declared together.
MCP_DESCRIPTIONS: dict[str, str] = {
    'ccb_contract': (
        'Return the operating rules, invariants and canonical step order for this tool. Call this first if you are unsure how to proceed, or after an unexpected result.'
    ),
    'ccb_channels': (
        'List every paper source (channel) with its availability, capabilities and the name of any credential it is missing. Credential values are never returned.'
    ),
    'ccb_find': (
        'Find papers on a topic. Queries the local library first and only fans out to channels on a miss, storing what it finds so the same paper is never searched for twice.'
    ),
    'ccb_get': (
        'Acquire one paper by identifier (DOI, arXiv id, OpenReview id, dblp key, PMID, URL or an existing work_id). Resolves locally first; re-running on a paper already held costs nothing.'
    ),
    'ccb_ask': (
        "Answer a question from the local corpus. Returns ranked passages with work_id and page anchors instead of prose, so any claim can be verified. Compose the answer yourself and cite the returned anchors. If 'grounded' is false, say the corpus does not cover the question rather than answering from memory."
    ),
    'ccb_open': (
        "Read a paper's stored full text. Never touches the network."
    ),
    'ccb_cite': (
        'Citation for one work in BibTeX, RIS, CSL-JSON or plain text, together with which source supplied each field and which fields no source provided.'
    ),
    'ccb_export': (
        'Bibliography for several works at once.'
    ),
    'ccb_stats': (
        'Corpus state: how many works, how many with PDFs and full text, evidence snapshots, and duplicate candidates awaiting a decision.'
    ),
    'ccb_topics_survey': (
        'Step 1 of topic generation. Map what the local corpus holds for a direction: works, years, venues with CCF ranks, terms. Tops the direction up from the channels when it is too thin to mine, and reports what it added. Returns sufficient=false when there is still too little evidence.'
    ),
    'ccb_topics_gaps': (
        'Step 2. The gap evidence for a survey: sentences where authors state limitations or future work (with work_id and page), sparse term pairs, and a tally by gap kind. This is evidence to read, not a conclusion.'
    ),
    'ccb_topics_candidates': (
        "Step 3. Ranked (evidence x novelty operator) topic candidates, with a score whose four parts are reported, and the local works that share each candidate's terms. Combinations already committed are excluded, which is what makes repeated mining non-repetitive."
    ),
    'ccb_topics_draft': (
        "Step 4. Commit to ONE candidate. Returns the section skeleton a paper of this kind needs — background, the four-step gap derivation, research questions, contributions, approach, expected experiments and datasets, anticipated criticism, references — with every claim's anchor attached. The tool does not write prose; compose each section from its anchors."
    ),
    'ccb_topics_rate': (
        "Step 5. The CCF estimate for a topic: upper bound, band, confidence, and the basis for every movement with its reason. A rule-based estimate from the recorded evidence, not an acceptance prediction. Name a target venue to check the estimate against that venue's own catalogue rank."
    ),
    'ccb_topics_save': (
        'Step 6. Commit a topic: export the Markdown draft and retire its de-duplication keys so the same combination is never proposed again.'
    ),
    'ccb_topics_list': (
        'Topics already mined, newest first, with what each consumed.'
    ),
}
