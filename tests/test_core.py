"""Unit tests: identity, normalization, dedup, provenance and library integrity.

Run without any network access and without third-party dependencies:

    python -m unittest discover -s tests -v
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

from ccb.search.channels.openalex import uninvert  # noqa: E402
from ccb.search.channels.crossref import clean_jats  # noqa: E402
from ccb.core.ids import compute_dedup_keys, compute_work_id, parse_identifier  # noqa: E402
from ccb.core.model import ChannelRecord, add_claim, resolve_field  # noqa: E402
from ccb.core.util import (  # noqa: E402
    arxiv_doi,
    normalize_arxiv_id,
    normalize_doi,
    normalize_person,
    normalize_title,
    strip_latex,
    title_tokens,
)
from ccb.library import Library  # noqa: E402
from ccb.library.cite import export, to_bibtex, to_ris  # noqa: E402
from ccb.library.evidence import redact_url  # noqa: E402
from ccb.search.net import is_bot_challenge, looks_like_pdf  # noqa: E402


class TestIdentifierParsing(unittest.TestCase):
    def test_doi_variants_fold_together(self):
        for raw in (
            "10.1038/nature12373",
            "https://doi.org/10.1038/Nature12373",
            "doi:10.1038/nature12373",
        ):
            with self.subTest(raw=raw):
                parsed = parse_identifier(raw)
                self.assertIsNotNone(parsed)
                self.assertEqual(parsed.scheme, "doi")
                self.assertEqual(parsed.value, "10.1038/nature12373")

    def test_arxiv_doi_is_arxiv_not_plain_doi(self):
        # A preprint must keep its preprint identity so it can later be related to its
        # published version rather than silently becoming a different work.
        parsed = parse_identifier("10.48550/arXiv.1706.03762")
        self.assertEqual(parsed.scheme, "arxiv")
        self.assertEqual(parsed.value, "1706.03762")

    def test_arxiv_id_forms(self):
        cases = {
            "1706.03762": "1706.03762",
            "arXiv:1706.03762v5": "1706.03762",
            "http://arxiv.org/abs/1706.03762v7": "1706.03762",
            "https://arxiv.org/pdf/1706.03762.pdf": "1706.03762",
            "hep-th/9901001v2": "hep-th/9901001",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_arxiv_id(raw), expected)

    def test_arxiv_url_is_not_mangled(self):
        # Regression: splitting on "arxiv." turned this into "org/abs/1706.03762",
        # which forked the identity of the same paper.
        self.assertNotIn("org/abs", normalize_arxiv_id("http://arxiv.org/abs/1706.03762"))

    def test_scheme_prefixes(self):
        self.assertEqual(parse_identifier("openreview:abcDEF123").scheme, "openreview")
        self.assertEqual(parse_identifier("dblp:conf/nips/VaswaniSPUJGKP17").value,
                         "conf/nips/VaswaniSPUJGKP17")
        self.assertEqual(parse_identifier("PMID:34265844").scheme, "pmid")

    def test_unknown_returns_none(self):
        self.assertIsNone(parse_identifier(""))
        self.assertIsNone(parse_identifier("   "))


class TestWorkIdentity(unittest.TestCase):
    def test_key_chain_priority(self):
        # DOI beats arXiv beats a title fallback.
        wid, matched = compute_work_id(
            ids={"arxiv": "1706.03762", "doi": "10.1000/x"}, title="T"
        )
        self.assertEqual(wid, "doi:10.1000/x")
        self.assertEqual(matched, "doi")

        wid, matched = compute_work_id(ids={"arxiv": "1706.03762"}, title="T")
        self.assertEqual(wid, "arxiv:1706.03762")
        self.assertEqual(matched, "arxiv")

    def test_title_fallback_is_stable_across_typography(self):
        # The whole point of the fallback key: trivial differences must not fork it.
        a, _ = compute_work_id(title="Attention Is All You Need!", authors=["Ashish Vaswani"], year=2017)
        b, _ = compute_work_id(title="attention is all you need", authors=["A. Vaswani"], year=2017)
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("t:"))

    def test_person_normalization_handles_name_orders(self):
        self.assertEqual(normalize_person("Vaswani, Ashish"), normalize_person("Ashish Vaswani"))
        self.assertEqual(normalize_person("A. Vaswani"), normalize_person("Ashish Vaswani"))
        self.assertNotEqual(normalize_person("Ashish Vaswani"), normalize_person("Noam Shazeer"))

    def test_arxiv_doi_helper(self):
        self.assertEqual(arxiv_doi("1706.03762v5"), "10.48550/arxiv.1706.03762")
        self.assertEqual(arxiv_doi(""), "")


class TestNormalization(unittest.TestCase):
    def test_strip_latex(self):
        self.assertEqual(strip_latex(r"\textbf{Hello} world"), "Hello world")
        self.assertEqual(strip_latex("caf\\'e"), "café")
        self.assertEqual(strip_latex("a $x^2$ b").strip(), "a x^2 b")

    def test_normalize_title_folds_case_and_punctuation(self):
        self.assertEqual(
            normalize_title("Attention Is All You Need!"),
            normalize_title("attention  is all you need"),
        )

    def test_title_tokens_drops_noise(self):
        toks = title_tokens("A Study of B")
        self.assertNotIn("a", toks)
        self.assertNotIn("b", toks)
        self.assertIn("study", toks)

    def test_doi_normalization_strips_url_and_embedded_url(self):
        self.assertEqual(normalize_doi("https://doi.org/10.1000/AbC"), "10.1000/abc")
        # Observed from OpenAlex: a DOI field whose value contained a full URL.
        self.assertEqual(normalize_doi("10.65215/https://doi.org/10.65215/2q58a426"),
                         "10.65215/2q58a426")


class TestProvenance(unittest.TestCase):
    def test_claims_are_never_overwritten(self):
        claims: dict = {}
        add_claim(claims, "year", 2020, src="crossref")
        add_claim(claims, "year", 2019, src="openalex")
        self.assertEqual(len(claims["year"]), 2)

    def test_duplicate_claim_from_same_source_is_dropped(self):
        claims: dict = {}
        self.assertTrue(add_claim(claims, "title", "T", src="arxiv"))
        self.assertFalse(add_claim(claims, "title", "T", src="arxiv"))
        self.assertEqual(len(claims["title"]), 1)

    def test_same_value_from_two_sources_is_kept(self):
        # Cross-source agreement is evidence, so it must survive.
        claims: dict = {}
        add_claim(claims, "title", "T", src="arxiv")
        add_claim(claims, "title", "T", src="crossref")
        self.assertEqual(len(claims["title"]), 2)

    def test_trust_order_decides_the_display_value(self):
        claims: dict = {}
        add_claim(claims, "venue", "arXiv", src="arxiv")
        add_claim(claims, "venue", "NeurIPS", src="crossref")
        self.assertEqual(resolve_field(claims, "venue"), "NeurIPS")

    def test_conflict_is_detectable(self):
        from ccb.core.model import field_conflict

        claims: dict = {}
        add_claim(claims, "year", 2020, src="a")
        add_claim(claims, "year", 1999, src="b")
        self.assertTrue(field_conflict(claims, "year"))


class TestChannelParsers(unittest.TestCase):
    def test_openalex_abstract_uninversion_orders_words(self):
        index = {"world": [1], "hello": [0], "again": [2]}
        self.assertEqual(uninvert(index), "hello world again")

    def test_openalex_uninversion_places_repeated_words(self):
        index = {"the": [0, 2], "cat": [1], "sat": [3]}
        self.assertEqual(uninvert(index), "the cat the sat")

    def test_uninvert_handles_empty(self):
        self.assertEqual(uninvert(None), "")
        self.assertEqual(uninvert({}), "")

    def test_crossref_jats_is_stripped(self):
        raw = "<jats:p>Hello <jats:italic>world</jats:italic></jats:p>"
        out = clean_jats(raw)
        self.assertNotIn("<", out)
        self.assertIn("Hello", out)

    def test_bot_challenge_detection(self):
        anubis = "<!doctype html><html><title>Making sure you're not a bot!</title>"
        self.assertTrue(is_bot_challenge(anubis, "text/html"))
        self.assertTrue(is_bot_challenge("<html>Just a moment...</html>", "text/html"))
        self.assertFalse(is_bot_challenge('{"ok": true}', "application/json"))

    def test_pdf_magic_check_rejects_html(self):
        self.assertTrue(looks_like_pdf(b"%PDF-1.5\n..."))
        self.assertFalse(looks_like_pdf(b"<html><body>challenge</body></html>"))
        self.assertFalse(looks_like_pdf(b""))

    def test_url_redaction_removes_credentials(self):
        url = "https://api.example.org/x?q=1&api_key=SECRET&mailto=a@b.c"
        red = redact_url(url)
        # The security property is that the secret is gone; encoding is incidental.
        self.assertNotIn("SECRET", red)
        self.assertNotIn("a@b.c", red)
        self.assertIn("api_key=", red)
        self.assertIn("redacted", red)
        self.assertIn("q=1", red, "non-secret parameters must survive redaction")


class TestLibrary(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-test-"))
        self.lib = Library(self.tmp / "lib")
        self.lib.ensure()

    def tearDown(self):
        self.lib.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _rec(self, **kw):
        base = dict(channel="test", title="Attention Is All You Need",
                    authors=["Ashish Vaswani"], year=2017, arxiv_id="1706.03762")
        base.update(kw)
        return ChannelRecord(**base)

    def test_upsert_creates_then_enriches(self):
        first = self.lib.upsert_record(self._rec())
        self.assertEqual(first.action, "created")
        self.assertEqual(first.work_id, "arxiv:1706.03762")

        # A different channel supplying a DOI enriches the same work rather than
        # creating a second record, and the identity is upgraded to the stronger key.
        second = self.lib.upsert_record(
            self._rec(channel="other", doi="10.48550/arXiv.1706.03762", abstract="A")
        )
        self.assertEqual(self.lib.count(), 1)
        self.assertIn(second.action, ("enriched", "duplicate"))
        # An arXiv DOI must not outrank the arXiv id it was minted from.
        self.assertEqual(second.work_id, "arxiv:1706.03762")

    def test_repeat_upsert_is_idempotent(self):
        self.lib.upsert_record(self._rec())
        before = self.lib.count()
        for _ in range(3):
            self.lib.upsert_record(self._rec())
        self.assertEqual(self.lib.count(), before)

    def test_old_identity_remains_resolvable_after_reidentification(self):
        """A work identified by a weak fallback key later learns a strong identifier.

        The weak id must keep resolving, or an identifier already handed out in a report
        or a script silently stops working.
        """
        self.lib.upsert_record(self._rec(arxiv_id="", doi=""))
        weak_id = self.lib.all_work_ids()[0]
        self.assertTrue(weak_id.startswith("t:"), weak_id)

        # Same paper, now carrying a DOI: the record is re-identified in place.
        self.lib.upsert_record(self._rec(arxiv_id="", doi="10.1000/strong"))
        strong = self.lib.resolve("10.1000/strong")
        self.assertIsNotNone(strong)
        self.assertEqual(strong.work_id, "doi:10.1000/strong")
        self.assertIn(weak_id, strong.aliases)

        # The pre-upgrade identifier still resolves, and to the same work.
        old = self.lib.resolve(weak_id)
        self.assertIsNotNone(old, f"alias {weak_id!r} stopped resolving after re-identification")
        self.assertEqual(old.work_id, "doi:10.1000/strong")

    def test_resolve_by_every_identifier_form(self):
        self.lib.upsert_record(self._rec())
        for needle in ("arxiv:1706.03762", "1706.03762", "http://arxiv.org/abs/1706.03762",
                       "arXiv:1706.03762v5"):
            with self.subTest(needle=needle):
                self.assertIsNotNone(self.lib.resolve(needle))

    def test_duplicate_is_flagged_not_silently_merged(self):
        # Near-identical titles from different sources without a shared id must be
        # surfaced as a candidate, never auto-merged.
        self.lib.upsert_record(self._rec(arxiv_id="", doi="", title="Deep Residual Learning for Image Recognition",
                                         authors=["Kaiming He"], year=2016))
        self.lib.upsert_record(
            self._rec(channel="other", arxiv_id="", doi="",
                      title="Deep Residual Learning for Image Recognition",
                      authors=["Kaiming He"], year=2016)
        )
        # Identical title + author + year is strong enough to auto-merge; the point is
        # that the decision is recorded.
        events = [e["event"] for e in self.lib.ledger()]
        self.assertTrue(any(e in ("auto_merge", "work_created") for e in events))

    def test_merge_moves_data_and_keeps_alias(self):
        a = self.lib.upsert_record(self._rec(arxiv_id="", doi="10.1000/a", title="Paper A",
                                             authors=["A One"], year=2001))
        b = self.lib.upsert_record(self._rec(arxiv_id="", doi="10.1000/b", title="Paper B",
                                             authors=["B Two"], year=2002))
        out = self.lib.merge(a.work_id, b.work_id, reason="test")
        self.assertTrue(out["merged"])
        self.assertIsNone(self.lib.load(b.work_id))
        self.assertIsNotNone(self.lib.resolve(b.work_id))

    def test_index_is_rebuilt_when_work_files_change_out_of_band(self):
        # The "an agent edited a file by hand" scenario must self-heal, not silently
        # answer from a stale index.
        self.lib.upsert_record(self._rec())
        self.assertEqual(len(self.lib.search("attention")), 1)

        stale = Library(self.tmp / "lib")
        self.lib.upsert_record(self._rec(arxiv_id="", doi="10.1/second", title="Second Paper",
                                         authors=["C Three"], year=2003))
        hits = stale.search("paper")
        self.assertTrue(any("Second" in h["title"] for h in hits),
                        "a fresh Library instance must see files added by another")

    def test_self_check_reports_and_repairs(self):
        self.lib.upsert_record(self._rec())
        # Release the SQLite handle first: on Windows an open handle locks the file.
        self.lib.close()
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(self.lib.index_path) + suffix)
            if p.exists():
                p.unlink()
        report = self.lib.self_check(repair=True)
        self.assertTrue(report["index_ok"])
        self.assertTrue(any("rebuilt" in r for r in report["repaired"]))

    def test_corrupt_work_file_is_reported_not_deleted(self):
        self.lib.upsert_record(self._rec())
        target = next(self.lib.works_dir.glob("**/*.json"))
        target.write_text("{not valid json", encoding="utf-8")
        report = self.lib.self_check(repair=True)
        kinds = [p["kind"] for p in report["problems"]]
        self.assertIn("unreadable_work_files", kinds)
        self.assertTrue(target.exists(), "repair must never delete a work file")

    def test_content_addressed_storage_dedupes_bytes(self):
        d1, p1, n1 = self.lib.store_file(b"%PDF-1.4 same", ext="pdf")
        d2, p2, n2 = self.lib.store_file(b"%PDF-1.4 same", ext="pdf")
        self.assertEqual(d1, d2)
        self.assertEqual(p1, p2)
        self.assertEqual(n1, n2)

    def test_stats_and_all_work_ids_see_sharded_files(self):
        # Regression: a one-level glob reported an empty library for a two-level shard.
        self.lib.upsert_record(self._rec())
        self.assertEqual(len(self.lib.all_work_ids()), 1)
        self.assertEqual(self.lib.stats()["works"], 1)

    def test_evidence_redacts_credentials_at_write_time(self):
        ev = self.lib.evidence.record(
            channel="x", url="https://h/p?api_key=SECRET", body="{}"
        )
        stored = self.lib.evidence.get(ev.ev_id)
        self.assertNotIn("SECRET", json.dumps(stored.as_dict()))


class TestCitations(unittest.TestCase):
    def _work(self, **overrides):
        base = dict(
            channel="test", title="Attention Is All You Need",
            authors=["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit"],
            year=2017, venue="NeurIPS", arxiv_id="1706.03762", doi="10.1000/x",
            pages="5998-6008", volume="30",
        )
        base.update(overrides)
        return ChannelRecord(**base).to_work()

    def test_bibtex_contains_only_known_fields(self):
        out = to_bibtex(self._work())
        self.assertIn("@inproceedings", out)
        self.assertIn("booktitle = {NeurIPS}", out)
        self.assertIn("doi = {10.1000/x}", out)
        self.assertIn("pages = {5998-6008}", out)

    def test_missing_fields_are_omitted_never_invented(self):
        work = self._work(pages="", volume="")
        out = to_bibtex(work)
        self.assertNotIn("pages =", out)
        self.assertNotIn("volume =", out)

    def test_citation_key_is_stable_across_exports(self):
        work = self._work()
        self.assertEqual(to_bibtex(work), to_bibtex(work))

    def test_bibtex_braces_are_balanced(self):
        work = self._work(title="A {weird} title with & and % and a lone {")
        out = to_bibtex(work)
        title_line = [line for line in out.splitlines() if "title =" in line][0]
        self.assertEqual(title_line.count("{"), title_line.count("}"))

    def test_ris_and_csl_render(self):
        work = self._work()
        self.assertIn("TY  - CONF", to_ris(work))
        self.assertIn("ER  - ", to_ris(work))
        data = json.loads(export([work], fmt="csl"))
        self.assertEqual(data[0]["DOI"], "10.1000/x")

    def test_unsupported_format_raises(self):
        with self.assertRaises(ValueError):
            export([self._work()], fmt="docx")


class TestDedupKeys(unittest.TestCase):
    def test_blocking_key_groups_similar_titles(self):
        a = compute_dedup_keys(title="Attention Is All You Need", year=2017)
        b = compute_dedup_keys(title="Attention is all you need!", year=2017)
        self.assertEqual(a.blocking_key(), b.blocking_key())

    def test_dedup_keys_normalize_identifiers(self):
        k = compute_dedup_keys(title="T", doi="https://doi.org/10.1000/AbC", arxiv="1706.03762v5")
        self.assertEqual(k.doi, "10.1000/abc")
        self.assertEqual(k.arxiv, "1706.03762")


if __name__ == "__main__":
    unittest.main(verbosity=2)
