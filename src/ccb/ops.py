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
