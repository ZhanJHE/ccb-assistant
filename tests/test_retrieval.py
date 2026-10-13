"""Tests for the L4 retrieval layer, extraction quality, and channel transparency.

No network, no third-party dependencies:

    python -m unittest discover -s tests
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ccb.search.channels.base import Channel, ChannelSpec  # noqa: E402
from ccb.search.channels.registry import Registry  # noqa: E402
from ccb.core.extract import assess_text_quality, _sentence_break_heuristic  # noqa: E402
from ccb.core.model import ChannelRecord  # noqa: E402
from ccb.library import Library  # noqa: E402
from ccb.library.passages import (  # noqa: E402
    BM25_K1,
    Passage,
    PassageIndex,
    build_index,
    chunk_text,
    split_pages,
    tokenize,
)
from ccb.search.net import credential, credential_available  # noqa: E402
from ccb.search.acquire import Resolver  # noqa: E402


class TestTokenizer(unittest.TestCase):
    def test_lowercases_and_stems_plurals(self):
        self.assertEqual(tokenize("Models"), ["model"])
        self.assertEqual(tokenize("models"), ["model"])
        self.assertEqual(tokenize("studies"), ["study"])

    def test_drops_stopwords_but_keeps_content(self):
        toks = tokenize("the attention of a transformer")
        self.assertNotIn("the", toks)
        self.assertNotIn("of", toks)
        self.assertIn("attention", toks)
        self.assertIn("transformer", toks)

    def test_keeps_stopwords_when_asked(self):
        self.assertIn("the", tokenize("the model", keep_stopwords=True))

    def test_short_words_are_not_stemmed_into_nonsense(self):
        # "gas" must not become "ga"; the length guard exists for this.
        self.assertEqual(tokenize("gas"), ["gas"])
        self.assertEqual(tokenize("bias"), ["bias"])

    def test_cjk_run_becomes_bigrams(self):
        toks = tokenize("注意力机制")
        self.assertIn("注意力机制", toks)
        self.assertIn("注意", toks)
        self.assertIn("机制", toks)

    def test_numbers_survive(self):
        self.assertIn("3.5", tokenize("version 3.5 released"))


class TestPageSplitting(unittest.TestCase):
    def test_form_feed_marks_page_boundaries(self):
        pages = split_pages("one\ftwo\fthree")
        self.assertEqual([p[0] for p in pages], [1, 2, 3])
        self.assertEqual(pages[1][1], "two")

    def test_absent_form_feed_reports_a_single_page(self):
        # Honest rather than guessed: a page number is never invented.
        pages = split_pages("no page breaks here")
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0][0], 1)

    def test_trailing_form_feed_is_dropped(self):
        pages = split_pages("one\ftwo\f")
        self.assertEqual(len(pages), 2)

    def test_empty_input(self):
        self.assertEqual(split_pages(""), [])


class TestChunking(unittest.TestCase):
    def test_chunks_carry_page_and_offsets(self):
        text = ("alpha " * 300) + "\f" + ("beta " * 300)
        passages = chunk_text(text, work_id="w1", passage_chars=500, overlap_chars=50)
        self.assertGreater(len(passages), 2)
        self.assertEqual({p.page for p in passages}, {1, 2})
        for p in passages:
            self.assertEqual(p.work_id, "w1")
            self.assertLess(p.start, p.end)
            self.assertTrue(p.text)

    def test_overlap_keeps_a_seam_sentence_whole(self):
        # A sentence straddling a boundary must appear intact in one passage.
        body = ("x " * 240) + "THE CRITICAL SENTENCE APPEARS HERE. " + ("y " * 240)
        passages = chunk_text(body, work_id="w1", passage_chars=500, overlap_chars=200)
        joined = " ".join(p.text for p in passages)
        self.assertIn("THE CRITICAL SENTENCE APPEARS HERE.", joined)

    def test_passage_ids_are_unique_and_ordered(self):
        passages = chunk_text("word " * 2000, work_id="w1")
        ids = [p.passage_id for p in passages]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, sorted(ids))

    def test_short_tail_chunk_is_kept_not_dropped(self):
        # Regression: the minimum-length guard discarded a page's final short chunk, so
        # a brief conclusion or closing sentence became unsearchable — the exact
        # "answer exists but cannot be found" failure this layer is meant to prevent.
        passages = chunk_text("intro paragraph\fshort tail about attention", work_id="w1")
        joined = " ".join(p.text for p in passages)
        self.assertIn("short tail about attention", joined)
        self.assertIn(2, {p.page for p in passages})

    def test_token_count_is_populated(self):
        passages = chunk_text("attention is all you need " * 100, work_id="w1")
        self.assertTrue(all(p.token_count > 0 for p in passages))


class TestRanking(unittest.TestCase):
    def setUp(self):
        docs = [
            ("w1", "The transformer relies on scaled dot-product attention."),
            ("w1", "Convolutional networks use pooling and kernels."),
            ("w2", "Attention mechanisms were introduced for machine translation."),
            ("w2", "Diffusion models generate images by denoising."),
        ]
        passages = [
            Passage(passage_id=f"p{i}", work_id=w, page=1, start=0, end=len(t), text=t)
            for i, (w, t) in enumerate(docs, start=1)
        ]
        self.index = PassageIndex(passages)
        self.index.set_metadata("w1", title="Transformer", year=2017)
        self.index.set_metadata("w2", title="Survey", year=2020)

    def test_relevant_passage_ranks_first(self):
        hits = self.index.search("attention", limit=4)
        self.assertTrue(hits)
        self.assertIn("attention", hits[0].passage.text.casefold())

    def test_irrelevant_query_returns_nothing(self):
        self.assertEqual(self.index.search("quantum chromodynamics"), [])

    def test_empty_query_returns_nothing(self):
        self.assertEqual(self.index.search(""), [])
        self.assertEqual(self.index.search("the of and"), [])

    def test_work_filter_restricts_results(self):
        hits = self.index.search("attention", limit=10, work_ids=["w2"])
        self.assertTrue(hits)
        self.assertTrue(all(h.passage.work_id == "w2" for h in hits))

    def test_max_per_work_enforces_diversity(self):
        hits = self.index.search("attention", limit=10, max_per_work=1)
        works = [h.passage.work_id for h in hits]
        self.assertEqual(len(works), len(set(works)))

    def test_citation_includes_work_and_page(self):
        hits = self.index.search("attention", limit=1)
        self.assertIn("w1", hits[0].citation)
        self.assertIn("p.1", hits[0].citation)
        self.assertIn("Transformer", hits[0].citation)

    def test_ranking_is_deterministic(self):
        a = [h.passage.passage_id for h in self.index.search("attention", limit=4)]
        b = [h.passage.passage_id for h in self.index.search("attention", limit=4)]
        self.assertEqual(a, b)

    def test_multiple_terms_beat_single_term_repetition(self):
        # A passage covering both query terms should outrank one repeating a single term.
        passages = [
            Passage(passage_id="a", work_id="w", page=1, start=0, end=1,
                    text="sparse attention routing " * 20),
            Passage(passage_id="b", work_id="w", page=1, start=0, end=1,
                    text="attention " * 40),
        ]
        idx = PassageIndex(passages)
        hits = idx.search("sparse attention routing", limit=2)
        self.assertEqual(hits[0].passage.passage_id, "a")

    def test_stats(self):
        s = self.index.stats()
        self.assertEqual(s["passages"], 4)
        self.assertEqual(s["works"], 2)
        self.assertGreater(s["unique_terms"], 0)

    def test_bm25_parameters_are_the_documented_defaults(self):
        self.assertAlmostEqual(BM25_K1, 1.5)


class TestExtractionQuality(unittest.TestCase):
    def test_jammed_text_is_detected(self):
        jammed = "Anattentionfunctioncanbedescribedasmappingaqueryandasetofkeyvaluepairs " * 20
        q = assess_text_quality(jammed)
        self.assertTrue(q.jammed)
        self.assertLess(q.score, 0.4)

    def test_healthy_text_scores_high(self):
        healthy = "This paper proposes the Transformer architecture based on attention. " * 30
        q = assess_text_quality(healthy)
        self.assertFalse(q.jammed)
        self.assertGreater(q.score, 0.85)

    def test_empty_text_scores_zero(self):
        q = assess_text_quality("")
        self.assertEqual(q.score, 0.0)
        self.assertFalse(q.jammed)

    def test_heuristic_restores_obvious_boundaries(self):
        # The repair can only use boundaries the text layer preserved: a lowercase ->
        # uppercase transition or a letter/digit change. Two jammed lowercase words
        # ("Anattention") cannot be split without a dictionary, and the module does not
        # pretend otherwise.
        fixed = _sentence_break_heuristic("AttentionIsAllYouNeed 2020 version")
        self.assertIn("Attention Is All You Need", fixed)
        self.assertIn("2020 version", fixed)
        self.assertGreater(
            assess_text_quality(fixed).score,
            assess_text_quality("AttentionIsAllYouNeed 2020 version").score,
        )

    def test_heuristic_does_not_run_words_together(self):
        # The repair must only add spaces; it must never delete characters.
        src = "MultiHeadAttention block"
        fixed = _sentence_break_heuristic(src)
        self.assertEqual(len(fixed) >= len(src), True)
        self.assertEqual(fixed.replace(" ", ""), src.replace(" ", ""))


class TestChannelTransparency(unittest.TestCase):
    """A channel that cannot run must degrade and explain, never fail the request."""

    def _spec(self, **kw):
        base = dict(name="needs_key", kind="http", caps=("search", "lookup"))
        base.update(kw)
        return ChannelSpec(**base)

    def test_missing_required_credential_reports_the_variable(self):
        chan = Channel()
        chan.spec = self._spec(auth="env:CCB_TEST_ABSENT_KEY")
        usable, reason = chan.available()
        self.assertFalse(usable)
        self.assertIn("CCB_TEST_ABSENT_KEY", reason)

    def test_optional_credential_does_not_block(self):
        chan = Channel()
        chan.spec = self._spec(auth="env:CCB_TEST_ABSENT_KEY?")
        usable, _ = chan.available()
        self.assertTrue(usable)

    def test_required_env_lists_only_mandatory_variables(self):
        chan = Channel()
        chan.spec = self._spec(auth="env:CCB_TEST_ABSENT_KEY")
        self.assertEqual(chan.spec.required_env(), ["CCB_TEST_ABSENT_KEY"])
        chan.spec = self._spec(auth="env:CCB_TEST_ABSENT_KEY?")
        self.assertEqual(chan.spec.required_env(), [])
        self.assertEqual(chan.spec.optional_env(), ["CCB_TEST_ABSENT_KEY"])

    def test_credential_value_never_reaches_the_report(self):
        import os

        os.environ["CCB_TEST_SECRET_KEY"] = "super-secret-value"
        try:
            chan = Channel()
            chan.spec = self._spec(auth="env:CCB_TEST_SECRET_KEY")
            import json

            rendered = json.dumps(chan.describe(), ensure_ascii=False)
            self.assertNotIn("super-secret-value", rendered)
            self.assertTrue(chan.available()[0])
            self.assertTrue(credential_available("CCB_TEST_SECRET_KEY"))
            self.assertEqual(credential("CCB_TEST_SECRET_KEY"), "super-secret-value")
        finally:
            os.environ.pop("CCB_TEST_SECRET_KEY", None)

    def test_unknown_credential_maps_to_no_channel(self):
        from ccb.search.net import credential_provider

        self.assertEqual(credential_provider("NOT_A_KNOWN_VAR"), "")
        self.assertEqual(credential_provider("S2_API_KEY"), "semantic_scholar")


class TestIdentifierVerification(unittest.TestCase):
    """The guard against a source answering a precise query with the wrong paper."""

    def _chan(self):
        chan = Channel()
        chan.spec = ChannelSpec(name="fake", kind="http", caps=("lookup",))
        return chan

    def test_wrong_doi_record_is_rejected(self):
        chan = self._chan()
        rec = ChannelRecord(channel="fake", title="Attention Is All You Need",
                            doi="10.65215/2q58a426")
        kept, rejected = chan.verify_identifier("10.48550/arXiv.1706.03762", [rec])
        self.assertEqual(kept, [])
        self.assertTrue(rejected)

    def test_matching_doi_record_is_kept(self):
        chan = self._chan()
        rec = ChannelRecord(channel="fake", title="T", doi="10.1038/nature12373")
        kept, rejected = chan.verify_identifier("10.1038/nature12373", [rec])
        self.assertEqual(len(kept), 1)
        self.assertEqual(rejected, [])

    def test_arxiv_id_matches_through_its_registered_doi(self):
        chan = self._chan()
        rec = ChannelRecord(channel="fake", title="T", doi="10.48550/arXiv.1706.03762")
        kept, _ = chan.verify_identifier("arxiv:1706.03762", [rec])
        self.assertEqual(len(kept), 1)

    def test_version_suffix_does_not_break_matching(self):
        chan = self._chan()
        rec = ChannelRecord(channel="fake", title="T", arxiv_id="1706.03762")
        kept, _ = chan.verify_identifier("arXiv:1706.03762v5", [rec])
        self.assertEqual(len(kept), 1)

    def test_title_and_url_identifiers_pass_through_unchecked(self):
        chan = self._chan()
        rec = ChannelRecord(channel="fake", title="Anything at all")
        kept, rejected = chan.verify_identifier("some paper title", [rec])
        self.assertEqual(len(kept), 1)
        self.assertEqual(rejected, [])


class TestAskGrounded(unittest.TestCase):
    """`ask` returns evidence with anchors, and never invents coverage."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-ask-"))
        self.lib = Library(self.tmp / "lib")
        self.lib.ensure()

    def tearDown(self):
        self.lib.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _add(self, work_id_doi: str, text: str, title: str) -> str:
        rec = ChannelRecord(
            channel="test", title=title, authors=["A Author"], year=2020, doi=work_id_doi
        )
        upsert = self.lib.upsert_record(rec)
        rel, chars = self.lib.store_fulltext(upsert.work_id, text)
        self.lib.attach_fulltext(upsert.work_id, rel_path=rel, chars=chars)
        return upsert.work_id

    def _resolver(self):
        resolver = Resolver(self.lib, Registry(evidence=self.lib.evidence), offline=True)
        # The registry owns an HTTP client but no socket is opened for offline use;
        # closing the library releases the SQLite handle so Windows can delete the
        # temp directory in tearDown.
        self.addCleanup(self.lib.close)
        return resolver

    def test_ask_retrieves_with_page_anchors(self):
        self._add("10.1000/a", "intro alpha\f" + ("scaled dot product attention " * 40),
                  "Paper A")
        out = self._resolver().ask("scaled dot product attention")
        self.assertTrue(out["grounded"])
        self.assertTrue(out["hits"])
        top = out["hits"][0]
        self.assertEqual(top["page"], 2)
        self.assertIn("p.2", top["citation"])
        self.assertIn("10.1000/a", top["citation"])

    def test_ask_reports_no_coverage_instead_of_guessing(self):
        self._add("10.1000/b", "entirely about databases and query planning", "Paper B")
        out = self._resolver().ask("reinforcement learning from human feedback")
        self.assertFalse(out["grounded"])
        self.assertEqual(out["hits"], [])
        self.assertIn("does not cover", out["note"].lower() + out.get("message", "").lower())

    def test_ask_over_empty_corpus_is_not_an_error_shape(self):
        out = self._resolver().ask("anything")
        self.assertFalse(out["grounded"])
        self.assertEqual(out["corpus"]["passages"], 0)
        self.assertIn("message", out)

    def test_ask_can_be_restricted_to_specific_works(self):
        a = self._add("10.1000/c", "attention in paper C", "Paper C")
        self._add("10.1000/d", "attention in paper D", "Paper D")
        out = self._resolver().ask("attention", work_ids=[a])
        self.assertTrue(out["hits"])
        self.assertTrue(all(h["work_id"] == a for h in out["hits"]))

    def test_ask_skips_works_without_fulltext_and_says_so(self):
        self._add("10.1000/e", "attention text here", "Has text")
        # A work with metadata but no stored text is not silently invisible: when the
        # corpus is searched wholesale it is reported as skipped, so an absent result is
        # distinguishable from an unsearchable one.
        self.lib.upsert_record(
            ChannelRecord(channel="test", title="No text", authors=["B"], year=2021,
                          doi="10.1000/f")
        )
        out = self._resolver().ask("attention")
        self.assertTrue(out["grounded"])
        self.assertIn("skipped", out)
        self.assertTrue(any("no stored full text" in s["reason"] for s in out["skipped"]))
        self.assertIn("doi:10.1000/f", [s["work_id"] for s in out["skipped"]])

    def test_passage_index_is_rebuilt_when_fulltext_changes(self):
        # Regression: a stale passage index made `ask` search text that was no longer on
        # disk after a re-extraction.
        wid = self._add("10.1000/g", "original text about cats", "Changing")
        work = self.lib.load(wid)
        first = self.lib.read_passages(work)
        self.assertTrue(any("cats" in p.text for p in first))

        rel, chars = self.lib.store_fulltext(wid, "replaced text about quantum optics")
        self.lib.attach_fulltext(wid, rel_path=rel, chars=chars)
        work = self.lib.load(wid)
        second = self.lib.read_passages(work)
        joined = " ".join(p.text for p in second)
        self.assertIn("quantum", joined)
        self.assertNotIn("cats", joined)

    def test_passages_are_not_rebuilt_when_text_is_unchanged(self):
        wid = self._add("10.1000/h", "stable text about attention", "Stable")
        work = self.lib.load(wid)
        first = self.lib.read_passages(work)
        # Ask the library for the path rather than reconstructing the escaped name.
        p = self.lib.passages_path(wid)
        self.assertTrue(p.exists())
        before = p.stat().st_mtime_ns
        second = self.lib.read_passages(work)
        self.assertEqual(len(first), len(second))
        self.assertEqual(p.stat().st_mtime_ns, before, "unchanged text must reuse the index")

    def test_build_index_helper_collects_metadata(self):
        wid = self._add("10.1000/i", "attention everywhere", "Meta Paper")
        work = self.lib.load(wid)
        idx = build_index([work], {wid: "attention everywhere"})
        hits = idx.search("attention", limit=1)
        self.assertTrue(hits)
        self.assertEqual(hits[0].title, "Meta Paper")


class TestCitationsClosed(unittest.TestCase):
    """`cite` output must be usable and honest about what is missing."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-cite-"))
        self.lib = Library(self.tmp / "lib")
        self.lib.ensure()

    def tearDown(self):
        self.lib.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_citation_records_field_provenance(self):
        from ccb.library.cite import to_bibtex

        rec = ChannelRecord(channel="crossref", title="A Paper", authors=["A One"],
                            year=2021, venue="NeurIPS", doi="10.1000/z")
        w = rec.to_work()
        out = to_bibtex(w)
        self.assertIn("@inproceedings", out)
        # Every field present in the entry came from a recorded claim.
        self.assertEqual(set(w.claims), {"title", "authors", "year", "venue", "doi"})

    def test_missing_doi_is_not_invented(self):
        from ccb.library.cite import to_bibtex

        rec = ChannelRecord(channel="arxiv", title="A Preprint", authors=["B Two"],
                            year=2022, arxiv_id="2201.00001")
        out = to_bibtex(rec.to_work())
        self.assertNotIn("doi =", out)
        self.assertIn("eprint = {2201.00001}", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
