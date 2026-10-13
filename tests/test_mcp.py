"""Tests for the MCP face and for the CLI/MCP parity the objective requires.

Both faces are adapters over one core, so these tests pin the property that matters:
the same call through MCP and through the CLI resolver produces the same answer.

    python -m unittest discover -s tests
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ccb.library import Library  # noqa: E402
from ccb.mcp_server import (  # noqa: E402
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    McpServer,
    _handle_protocol,
    serve,
    tool_definitions,
)
from ccb.core.model import ChannelRecord  # noqa: E402


def _call(server: McpServer, msg_id: int, name: str, args: dict) -> dict:
    """Send one tools/call through the protocol layer and decode the payload.

    The server instance is passed in explicitly rather than patched into module state,
    so tests cannot leak a server into each other.
    """
    response = _handle_protocol(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        },
        server,
    )
    assert response is not None
    if "error" in response:
        return response["error"]
    return json.loads(response["result"]["content"][0]["text"])


class TestMcpProtocol(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-mcp-"))
        self.server = McpServer(self.tmp / "lib")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        self.server.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _add(self, doi: str, title: str, text: str = "") -> str:
        upsert = self.server.library.upsert_record(
            ChannelRecord(channel="test", title=title, authors=["A Author"], year=2020, doi=doi)
        )
        if text:
            rel, chars = self.server.library.store_fulltext(upsert.work_id, text)
            self.server.library.attach_fulltext(upsert.work_id, rel_path=rel, chars=chars)
        return upsert.work_id

    # ---------------- protocol level ---------------- #

    def test_initialize_reports_protocol_and_server_info(self):
        resp = _handle_protocol(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, self.server
        )
        self.assertEqual(resp["jsonrpc"], "2.0")
        self.assertEqual(resp["id"], 1)
        self.assertIn("protocolVersion", resp["result"])
        self.assertEqual(resp["result"]["serverInfo"]["name"], "ccb")

    def test_notifications_get_no_response(self):
        self.assertIsNone(
            _handle_protocol({"jsonrpc": "2.0", "method": "notifications/initialized"}, self.server)
        )
        # A notification with no id must not produce a reply even for a real call.
        self.assertIsNone(
            _handle_protocol(
                {"jsonrpc": "2.0", "method": "tools/call",
                 "params": {"name": "ccb_stats", "arguments": {}}},
                self.server,
            )
        )

    def test_tools_list_is_non_empty_and_well_formed(self):
        resp = _handle_protocol(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, self.server
        )
        tools = resp["result"]["tools"]
        self.assertGreaterEqual(len(tools), 8)
        names = {t["name"] for t in tools}
        for expected in ("ccb_find", "ccb_get", "ccb_ask", "ccb_open", "ccb_cite", "ccb_contract"):
            self.assertIn(expected, names)
        for t in tools:
            self.assertTrue(t["description"], f"{t['name']} has no description")
            self.assertEqual(t["inputSchema"]["type"], "object")

    def test_unknown_method_is_an_error_not_a_crash(self):
        resp = _handle_protocol(
            {"jsonrpc": "2.0", "id": 3, "method": "does/not/exist"}, self.server
        )
        self.assertEqual(resp["error"]["code"], METHOD_NOT_FOUND)

    def test_unknown_tool_is_an_error(self):
        err = _call(self.server, 4, "ccb_nonexistent", {})
        self.assertEqual(err["code"], METHOD_NOT_FOUND)

    def test_missing_required_parameter_is_rejected_clearly(self):
        err = _call(self.server, 5, "ccb_get", {})
        self.assertEqual(err["code"], INVALID_PARAMS)
        self.assertIn("identifier", err["message"])

    def test_ping(self):
        resp = _handle_protocol({"jsonrpc": "2.0", "id": 6, "method": "ping"}, self.server)
        self.assertEqual(resp["result"], {})

    def test_batch_request_over_stdio_returns_a_batch(self):
        inp = io.StringIO(
            json.dumps(
                [
                    {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                ]
            )
            + "\n"
        )
        out = io.StringIO()
        code = serve(library_root=self.tmp / "lib2", stdin=inp, stdout=out)
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue().strip())
        self.assertIsInstance(payload, list)
        self.assertEqual([r["id"] for r in payload], [1, 2])

    def test_malformed_json_yields_a_parse_error_and_the_stream_survives(self):
        inp = io.StringIO("not json\n" + json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}) + "\n")
        out = io.StringIO()
        serve(library_root=self.tmp / "lib3", stdin=inp, stdout=out)
        lines = [json.loads(line) for line in out.getvalue().strip().splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertIn("error", lines[0])
        self.assertEqual(lines[1]["id"], 9)

    # ---------------- tool level ---------------- #

    def test_stats_reports_the_corpus(self):
        self._add("10.1000/a", "Paper A", "attention text")
        stats = _call(self.server, 10, "ccb_stats", {})
        self.assertEqual(stats["works"], 1)
        self.assertEqual(stats["with_fulltext"], 1)

    def test_ask_returns_page_anchored_passages(self):
        self._add("10.1000/b", "Paper B", "intro\fscaled dot product attention matters")
        out = _call(self.server, 11, "ccb_ask", {"query": "scaled dot product attention"})
        self.assertTrue(out["grounded"])
        self.assertEqual(out["hits"][0]["page"], 2)
        self.assertIn("p.2", out["hits"][0]["citation"])

    def test_ask_without_coverage_says_so(self):
        self._add("10.1000/c", "Paper C", "databases and indexing")
        out = _call(self.server, 12, "ccb_ask", {"query": "protein folding"})
        self.assertFalse(out["grounded"])
        self.assertEqual(out["hits"], [])

    def test_open_returns_text_and_flags_truncation(self):
        self._add("10.1000/d", "Paper D", "x" * 500)
        out = _call(self.server, 13, "ccb_open", {"identifier": "10.1000/d", "head": 100})
        self.assertEqual(out["chars"], 100)
        self.assertEqual(out["total_chars"], 500)
        self.assertTrue(out["truncated"])

    def test_open_on_missing_work_reports_a_structured_error(self):
        out = _call(self.server, 14, "ccb_open", {"identifier": "10.9999/nope"})
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "not_found")

    def test_open_without_fulltext_distinguishes_the_two_cases(self):
        self._add("10.1000/e", "Paper E")  # no text stored
        out = _call(self.server, 15, "ccb_open", {"identifier": "10.1000/e"})
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "no_fulltext")
        self.assertIn("with_pdf", out["message"])

    def test_cite_returns_citation_and_provenance(self):
        self._add("10.1000/f", "Paper F")
        out = _call(self.server, 16, "ccb_cite", {"identifier": "10.1000/f", "format": "bibtex"})
        self.assertIn("@", out["citation"])
        self.assertIn("title", out["provenance"])
        self.assertEqual(out["provenance"]["title"], ["test"])

    def test_export_handles_unknown_ids_without_failing(self):
        self._add("10.1000/g", "Paper G")
        out = _call(self.server, 17, "ccb_export", {"work_ids": ["10.1000/g", "10.9999/missing"]})
        self.assertEqual(out["entries"], 1)
        self.assertEqual(out["not_found"], ["10.9999/missing"])

    def test_contract_is_exposed_through_mcp(self):
        out = _call(self.server, 18, "ccb_contract", {})
        ids = {i["id"] for i in out["invariants"]}
        self.assertIn("local-first", ids)
        self.assertIn("no-overwrite", ids)

    def test_channels_report_never_leaks_credential_values(self):
        import os

        os.environ["S2_API_KEY"] = "mcp-secret-value"
        try:
            out = _call(self.server, 19, "ccb_channels", {})
            rendered = json.dumps(out, ensure_ascii=False)
            self.assertNotIn("mcp-secret-value", rendered)
            self.assertIn("S2_API_KEY", rendered)
        finally:
            os.environ.pop("S2_API_KEY", None)


class TestCliMcpParity(unittest.TestCase):
    """The two faces must not diverge: same core, same answer."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-parity-"))
        self.lib = Library(self.tmp / "lib")
        self.lib.ensure()
        self.server = McpServer(self.tmp / "lib")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        self.server.close()
        self.lib.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stats_agree_between_faces(self):
        for doi, title in (("10.1000/x", "X"), ("10.1000/y", "Y")):
            self.lib.upsert_record(
                ChannelRecord(channel="test", title=title, authors=["A"], year=2020, doi=doi)
            )
        self.lib.close()  # let the MCP server reopen the same corpus
        cli_side = Library(self.tmp / "lib")
        try:
            cli_stats = cli_side.stats()
            mcp_stats = _call(self.server, 1, "ccb_stats", {})
            self.assertEqual(cli_stats["works"], mcp_stats["works"])
            self.assertEqual(cli_stats["with_pdf"], mcp_stats["with_pdf"])
        finally:
            cli_side.close()

    def test_ask_agrees_between_faces(self):
        upsert = self.lib.upsert_record(
            ChannelRecord(channel="test", title="Parity", authors=["A"], year=2021, doi="10.1000/p")
        )
        rel, chars = self.lib.store_fulltext(upsert.work_id, "intro\fthe parity passage about attention")
        self.lib.attach_fulltext(upsert.work_id, rel_path=rel, chars=chars)
        self.lib.close()

        from ccb.search.channels import Registry
        from ccb.search.acquire import Resolver

        cli_side = Library(self.tmp / "lib")
        try:
            cli_res = Resolver(cli_side, Registry(evidence=cli_side.evidence), offline=True)
            cli_out = cli_res.ask("parity passage attention")
        finally:
            cli_side.close()
        mcp_out = _call(self.server, 2, "ccb_ask", {"query": "parity passage attention"})

        self.assertEqual(cli_out["grounded"], mcp_out["grounded"])
        self.assertEqual(
            [h["work_id"] for h in cli_out["hits"]],
            [h["work_id"] for h in mcp_out["hits"]],
        )
        self.assertEqual([h["page"] for h in cli_out["hits"]], [h["page"] for h in mcp_out["hits"]])

    def test_tool_definitions_are_stable(self):
        # The tool list is part of the contract surface; a silent rename would break
        # every registered client, so the names are pinned. Topic generation is
        # deliberately several tools rather than one: the agent has to read the gap
        # evidence before choosing, and choose before drafting.
        #
        # Compared as a set: the names are the promise, the order is presentation, and
        # the list is now derived from the operation table rather than hand-written here.
        names = {t["name"] for t in tool_definitions()}
        self.assertEqual(
            names,
            {
                "ccb_contract",
                "ccb_channels",
                "ccb_find",
                "ccb_get",
                "ccb_ask",
                "ccb_open",
                "ccb_cite",
                "ccb_export",
                "ccb_stats",
                "ccb_topics_survey",
                "ccb_topics_gaps",
                "ccb_topics_candidates",
                "ccb_topics_draft",
                "ccb_topics_rate",
                "ccb_topics_save",
                "ccb_topics_list",
            },
        )

    def test_every_advertised_tool_has_a_handler(self):
        """An advertised tool with no implementation is a client-side crash."""
        from ccb.mcp_server import McpServer

        with tempfile.TemporaryDirectory() as tmp:
            server = McpServer(Path(tmp) / "lib")
            try:
                for entry in tool_definitions():
                    with self.subTest(tool=entry["name"]):
                        handler = getattr(
                            server, f"_tool_{entry['name'].removeprefix('ccb_')}", None
                        )
                        self.assertIsNotNone(handler, f"{entry['name']} has no handler")
            finally:
                server.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
