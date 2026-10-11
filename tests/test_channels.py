"""Channel-integration tests: the four channel *kinds* the objective names.

An http channel, a cli channel, an mcp channel and a manual file must all be usable
through one interface, with credentials and gating transparent. The MCP path in
particular had a real defect (an unbound-method borrow silently shifted every argument
and returned nothing with no error), so it is exercised end to end here.

    python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lit.search.channels.base import ChannelSpec  # noqa: E402
from lit.search.channels.generic import (  # noqa: E402
    GenericCliChannel,
    GenericHttpChannel,
    GenericMcpChannel,
    _dig,
    _unwrap_mcp_content,
)
from lit.search.channels.registry import Registry  # noqa: E402
from lit.library.evidence import EvidenceStore  # noqa: E402
from lit.library import Library  # noqa: E402
from lit.search.acquire import Resolver  # noqa: E402

PROBE_MCP = ROOT / "tools" / "probe_mcp_source.py"


class TestPathResolution(unittest.TestCase):
    """`_dig` backs every declarative channel, so its edge cases matter."""

    def test_simple_and_nested(self):
        data = {"a": {"b": {"c": 1}}}
        self.assertEqual(_dig(data, "a.b.c"), 1)
        self.assertEqual(_dig(data, "a.b"), {"c": 1})

    def test_list_index(self):
        data = {"r": [{"t": "first"}, {"t": "second"}]}
        self.assertEqual(_dig(data, "r.0.t"), "first")
        self.assertEqual(_dig(data, "r.1.t"), "second")

    def test_wildcard_takes_first(self):
        self.assertEqual(_dig({"r": [{"t": "x"}]}, "r.*.t"), "x")

    def test_recursive_search_for_varying_envelopes(self):
        # Some APIs nest the payload at a depth that changes between responses.
        self.assertEqual(_dig({"x": {"y": {"total": 7}}}, "@total"), 7)
        self.assertEqual(_dig({"a": [{"total": 3}]}, "@total"), 3)

    def test_missing_paths_return_the_default_without_raising(self):
        self.assertIsNone(_dig({"a": 1}, "a.b.c"))
        self.assertIsNone(_dig({"a": 1}, "nope"))
        self.assertEqual(_dig({}, "", "fallback"), "fallback")

    def test_index_out_of_range_is_safe(self):
        self.assertIsNone(_dig({"r": [1]}, "r.5"))


class TestMcpContentUnwrap(unittest.TestCase):
    def test_unwraps_json_text_block(self):
        payload = {"content": [{"type": "text", "text": json.dumps({"papers": [{"title": "T"}]})}]}
        out = _unwrap_mcp_content(payload)
        self.assertEqual(out["papers"][0]["title"], "T")

    def test_non_json_text_is_preserved(self):
        out = _unwrap_mcp_content({"content": [{"type": "text", "text": "plain answer"}]})
        self.assertEqual(out["text"], "plain answer")

    def test_object_without_content_is_returned_as_is(self):
        payload = {"papers": [{"title": "T"}]}
        self.assertIs(_unwrap_mcp_content(payload), payload)

    def test_empty_content_falls_back(self):
        payload = {"content": []}
        self.assertIs(_unwrap_mcp_content(payload), payload)


class TestDeclarativeChannels(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lit-chan-"))
        self.ev = EvidenceStore(self.tmp / "evidence")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------- http ---------------- #

    def test_http_channel_maps_a_nested_envelope(self):
        decl = {
            "kind": "http",
            "url": "https://example.invalid/api?q={query}",
            "caps": ["search"],
            "map": {
                "items": "result.hits.hit",
                "total": "result.hits.@total",
                "title": "info.title",
                "authors": "info.authors.author",
                "author_name": "text",
                "year": "info.year",
                "venue": "info.venue",
                "doi": "info.doi",
            },
        }
        chan = GenericHttpChannel("declared", decl, evidence=self.ev)
        payload = {
            "result": {
                "hits": {
                    "@total": "12",
                    "hit": [
                        {
                            "info": {
                                "title": "A Declared Paper",
                                "authors": {"author": [{"text": "A One"}, {"text": "B Two"}]},
                                "year": "2019",
                                "venue": "NeurIPS",
                                "doi": "10.1000/decl",
                            }
                        }
                    ],
                }
            }
        }
        res = type("R", (), {})()
        from lit.search.channels.base import ChannelResult

        res = ChannelResult("declared")
        chan._extract = None  # guard: http channel must use its own mapper
        rec = chan._map_item(payload["result"]["hits"]["hit"][0], decl["map"], "ev_x")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.title, "A Declared Paper")
        self.assertEqual(rec.authors, ["A One", "B Two"])
        self.assertEqual(rec.year, 2019)
        self.assertEqual(rec.venue, "NeurIPS")
        self.assertEqual(rec.doi, "10.1000/decl")

    # ---------------- cli ---------------- #

    def test_cli_channel_normalises_the_documented_envelope(self):
        decl = {"kind": "cli", "command": "definitely-not-installed", "caps": ["search"]}
        chan = GenericCliChannel("local", decl, evidence=self.ev)
        from lit.search.channels.base import ChannelResult

        res = ChannelResult("local")
        chan._extract(
            {
                "papers": [
                    {"title": "From CLI", "authors": ["C Three"], "published_date": "2021-05-01",
                     "pdf_url": "https://example.invalid/p.pdf", "source": "arxiv",
                     "paper_id": "2105.00001"}
                ],
                "total": 42,
                "errors": {"dblp": "gated"},
            },
            res,
            limit=5,
            mapping={},
        )
        self.assertEqual(len(res.records), 1)
        self.assertEqual(res.records[0].title, "From CLI")
        self.assertEqual(res.records[0].year, 2021)
        self.assertEqual(res.total_available, 42)
        self.assertTrue(any("gated" in w for w in res.warnings))
        self.assertEqual(res.records[0].extras["native_id"], "2105.00001")

    def test_cli_channel_accepts_a_bare_list(self):
        chan = GenericCliChannel("local", {"kind": "cli", "command": "x"}, evidence=self.ev)
        from lit.search.channels.base import ChannelResult

        res = ChannelResult("local")
        chan._extract([{"title": "Bare"}], res, limit=5, mapping={})
        self.assertEqual(len(res.records), 1)

    def test_cli_channel_reports_a_non_list_payload_instead_of_crashing(self):
        chan = GenericCliChannel("local", {"kind": "cli", "command": "x"}, evidence=self.ev)
        from lit.search.channels.base import ChannelResult

        # An unrecognised envelope must be an error, not an empty result: "this source
        # has nothing" and "I could not read this source" are different facts.
        res = ChannelResult("local")
        chan._extract({"unexpected": "shape"}, res, limit=5, mapping={})
        self.assertIn("record list", res.error)
        self.assertIn("unexpected", res.error)

        # A known key holding the wrong type names the problem specifically.
        res2 = ChannelResult("local")
        chan._extract({"papers": "not a list"}, res2, limit=5, mapping={})
        self.assertIn("expected a list", res2.error)

        # A scalar payload is reported too.
        res3 = ChannelResult("local")
        chan._extract(42, res3, limit=5, mapping={})
        self.assertTrue(res3.error)

    def test_empty_but_valid_envelope_is_not_an_error(self):
        chan = GenericCliChannel("local", {"kind": "cli", "command": "x"}, evidence=self.ev)
        from lit.search.channels.base import ChannelResult

        res = ChannelResult("local")
        chan._extract({"papers": []}, res, limit=5, mapping={})
        self.assertEqual(res.error, "")
        self.assertEqual(res.records, [])

    def test_missing_command_makes_the_channel_unavailable_not_fatal(self):
        chan = GenericCliChannel(
            "local", {"kind": "cli", "command": "definitely-not-installed-xyz"}, evidence=self.ev
        )
        usable, reason = chan.available()
        self.assertFalse(usable)
        self.assertIn("not found", reason)

    # ---------------- mcp ---------------- #

    def test_mcp_channel_shares_one_extractor_with_the_cli_channel(self):
        # Regression: this used to call GenericCliChannel._extract unbound, shifting
        # every argument and returning an empty result with no error at all.
        chan = GenericMcpChannel("probe", {"kind": "mcp", "command": ["x"], "caps": ["search"]},
                                 evidence=self.ev)
        self.assertTrue(callable(chan._extract))
        mro_names = [c.__name__ for c in type(chan).__mro__]
        self.assertIn("_ResponseExtractor", mro_names)
        self.assertIn("_ResponseExtractor", [c.__name__ for c in GenericCliChannel.__mro__])

    @unittest.skipUnless(PROBE_MCP.exists(), "probe MCP fixture not present")
    def test_mcp_channel_end_to_end_against_a_real_stdio_server(self):
        decl = {
            "kind": "mcp",
            "command": [sys.executable, str(PROBE_MCP)],
            "caps": ["search", "lookup"],
            "auth": "none",
            "search_tool": "search_papers",
            "query_arg": "query",
            "limit_arg": "limit",
            "map": {"items": "papers", "title": "title", "authors": "authors",
                    "year": "year", "venue": "venue"},
        }
        chan = GenericMcpChannel("probe", decl, evidence=self.ev)
        usable, reason = chan.available()
        self.assertTrue(usable, reason)
        res = chan.search("scaling laws", limit=3)
        self.assertEqual(res.error, "")
        self.assertEqual(len(res.records), 1, "MCP payload was not normalised")
        rec = res.records[0]
        self.assertEqual(rec.title, "Scaling Laws for Neural Language Models")
        self.assertEqual(rec.year, 2020)
        self.assertEqual(rec.authors[0], "Jared Kaplan")
        # The raw stdio exchange is snapshotted like any other channel call.
        self.assertTrue(res.ev_id)
        self.assertIsNotNone(self.ev.get(res.ev_id))


class TestRegistryWithDeclaredChannels(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lit-reg-"))
        self.cfg = self.tmp / "channels.yaml"
        self.lib = Library(self.tmp / "lib")
        self.lib.ensure()

    def tearDown(self):
        self.lib.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_declared_http_channel_is_registered_and_routed(self):
        self.cfg.write_text(
            "channels:\n"
            "  extra_source:\n"
            "    kind: http\n"
            "    url: 'https://example.invalid/api?q={query}'\n"
            "    caps: [search, lookup]\n"
            "    auth: env:LIT_TEST_ABSENT?\n",
            encoding="utf-8",
        )
        reg = Registry(evidence=self.lib.evidence, config_paths=[self.cfg])
        self.assertIn("extra_source", reg.names())
        self.assertIn("extra_source", [c.name for c in reg.search_channels("auto")])
        # An optional credential must not make it unavailable.
        chan = reg.get("extra_source")
        self.assertTrue(chan.available()[0])

    def test_declared_channel_with_missing_required_key_degrades_with_reason(self):
        self.cfg.write_text(
            "channels:\n"
            "  keyed_source:\n"
            "    kind: http\n"
            "    url: 'https://example.invalid/api?q={query}'\n"
            "    caps: [search]\n"
            "    auth: env:LIT_TEST_ABSENT_KEY\n",
            encoding="utf-8",
        )
        reg = Registry(evidence=self.lib.evidence, config_paths=[self.cfg])
        chan = reg.get("keyed_source")
        usable, reason = chan.available()
        self.assertFalse(usable)
        self.assertIn("LIT_TEST_ABSENT_KEY", reason)
        summary = reg.availability_summary()
        self.assertIn("keyed_source", summary["unavailable"])
        # Everything else still routes, so one missing key cannot break the fan-out.
        self.assertTrue(summary["usable"])

    def test_orphaned_credential_is_reported(self):
        import os

        os.environ["S2_API_KEY"] = "orphan-test-value"
        try:
            reg = Registry(evidence=self.lib.evidence, config_paths=[])
            summary = reg.availability_summary()
            self.assertNotIn("orphan-test-value", json.dumps(summary))
            self.assertIn("credentials_without_channel", summary)
            self.assertEqual(
                summary["credentials_without_channel"].get("S2_API_KEY"), "semantic_scholar"
            )
        finally:
            os.environ.pop("S2_API_KEY", None)


class TestAllFourKindsThroughOneInterface(unittest.TestCase):
    """http, cli, mcp and manual must be indistinguishable to the resolver."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lit-kinds-"))
        self.lib = Library(self.tmp / "lib")
        self.lib.ensure()
        self.ev = self.lib.evidence

    def tearDown(self):
        self.lib.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _protocol_only_records(self):
        """Call each generic channel's normaliser directly on a representative payload."""
        from lit.search.channels.base import ChannelResult

        out = {}
        http_map = {"items": "results", "title": "title", "year": "year"}
        http = GenericHttpChannel(
            "http_kind", {"kind": "http", "url": "https://x.invalid", "map": http_map},
            evidence=self.ev,
        )
        http_rec = http._map_item(http_map and {"title": "Http Paper", "year": 2018}, http_map, "e")
        out["http"] = http_rec

        cli = GenericCliChannel("cli_kind", {"kind": "cli", "command": "x"}, evidence=self.ev)
        cli_res = ChannelResult("cli_kind")
        cli._extract({"papers": [{"title": "Cli Paper"}]}, cli_res, limit=5, mapping={})
        out["cli"] = cli_res.records[0] if cli_res.records else None

        mcp = GenericMcpChannel("mcp_kind", {"kind": "mcp", "command": ["x"]}, evidence=self.ev)
        mcp_res = ChannelResult("mcp_kind")
        mcp._extract(
            {"content": [{"type": "text", "text": json.dumps({"papers": [{"title": "Mcp Paper"}]})}]},
            mcp_res,
            limit=5,
            mapping={},
        )
        out["mcp"] = mcp_res.records[0] if mcp_res.records else None
        return out

    def test_every_kind_produces_a_normalised_record(self):
        recs = self._protocol_only_records()
        for kind, rec in recs.items():
            with self.subTest(kind=kind):
                self.assertIsNotNone(rec, f"{kind} channel produced no record")
                self.assertTrue(rec.title)
                self.assertEqual(rec.channel, f"{kind}_kind")

    def test_records_from_every_kind_enter_the_same_library(self):
        recs = self._protocol_only_records()
        works = []
        for rec in recs.values():
            upsert = self.lib.upsert_record(rec)
            works.append(upsert.work_id)
        self.assertEqual(len(works), len(set(works)), "distinct papers must not collide")
        for wid in works:
            self.assertIsNotNone(self.lib.resolve(wid))

    def test_manual_kind_enters_the_same_pipeline(self):
        from lit.core.model import ChannelRecord

        rec = ChannelRecord(channel="manual", title="Hand-Supplied Paper",
                            authors=["D Four"], year=2023)
        upsert = self.lib.upsert_record(rec)
        digest, rel, size = self.lib.store_file(b"%PDF-1.4 hand-supplied", ext="pdf")
        self.lib.attach_file(upsert.work_id, channel="manual", sha256=digest,
                             rel_path=rel, size=size)
        work = self.lib.load(upsert.work_id)
        self.assertTrue(work.has_pdf())
        # A manual record is a first-class citizen: it resolves, searches and exports.
        self.assertTrue(self.lib.search("Hand-Supplied"))
        self.assertIn("Hand-Supplied Paper", self.lib.export_bibtex([upsert.work_id]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
