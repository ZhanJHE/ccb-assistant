"""Tests for module three: the CCF catalogue, gap mining, and topic generation.

Everything here runs offline and without third-party dependencies, and every
assertion that matters is about a *property* rather than a golden string:

* the catalogue never guesses a rank it does not have;
* term extraction is a pure function of the text, so the same corpus yields the same
  terms in the same order;
* a topic cannot be produced without an anchor, and every anchor resolves to a work
  the library actually holds;
* the rating is recomputable from its stated basis;
* a committed topic's de-duplication key retires that combination.

    python -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ccb.core.model import ChannelRecord  # noqa: E402
from ccb.library import Library  # noqa: E402
from ccb.topics import candidates as candidates_mod  # noqa: E402
from ccb.topics import ccf as ccf_mod  # noqa: E402
from ccb.topics import draft as draft_mod  # noqa: E402
from ccb.topics import gaps as gaps_mod  # noqa: E402
from ccb.topics import operators as operators_mod  # noqa: E402
from ccb.topics import rating as rating_mod  # noqa: E402
from ccb.topics import store as store_mod  # noqa: E402
from ccb.topics import survey as survey_mod  # noqa: E402
from ccb.topics import terms as terms_mod  # noqa: E402

# Two clusters that share "molecular" and almost nothing else. This is what a
# recombination opening looks like: both concepts are common in the direction, and
# they never appear in the same paper.
_TITLES = [
    "Transformer architectures for molecular property regression",
    "Transformer pretraining on molecular spectra",
    "Transformer decoding of molecular graphs",
    "Transformer distillation for molecular screening",
    "Transformer pruning in molecular pipelines",
    "Transformer interpretability for molecular design",
    "Protein folding with molecular dynamics",
    "Protein docking via molecular simulations",
    "Protein design using molecular sketches",
    "Protein stability from molecular descriptors",
    "Protein ensembles in molecular mechanics",
    "Protein interfaces by molecular contact maps",
]

_ABSTRACTS = [
    "We evaluate on the QM9 dataset and compare with SchNet. A key limitation is that "
    "our method does not scale to large systems.",
    "We study molecular systems on the MD17 benchmark. Future work will address transfer "
    "to unseen proteins.",
    "Our approach assumes that molecular structures are static, an idealization we "
    "acknowledge. We compare with DimeNet.",
    "Few works study molecular interpretability. This remains an open problem.",
]


def _make_library(root: Path) -> Library:
    lib = Library(root / "lib")
    lib.ensure()
    for i, title in enumerate(_TITLES):
        lib.upsert_record(
            ChannelRecord(
                channel="manual",
                title=title,
                authors=[f"Author {i}"],
                year=2020 + i % 4,
                venue=["NeurIPS", "ICML", "CVPR", "Journal of Machine Learning Research"][i % 4],
                doi=f"10.1000/topics.{i}",
                abstract=_ABSTRACTS[i % len(_ABSTRACTS)],
            )
        )
    return lib


@contextmanager
def _library():
    """A populated library in a temp directory, closed before the directory goes.

    On Windows the SQLite index holds an open handle, and an unclosed library makes
    the temporary directory undeletable.
    """
    with tempfile.TemporaryDirectory() as tmp:
        lib = _make_library(Path(tmp))
        try:
            yield lib
        finally:
            lib.close()


class TestCcfCatalogue(unittest.TestCase):
    def test_bundled_catalogue_loads_and_self_checks(self):
        cat = ccf_mod.CcfCatalog.load()
        self.assertGreater(len(cat.venues), 50)
        report = cat.verify()
        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual(report["duplicates"], [])

    def test_exact_abbreviation_matches(self):
        cat = ccf_mod.CcfCatalog.load()
        self.assertEqual(cat.rank_of("NeurIPS"), "A")
        self.assertEqual(cat.rank_of("CVPR"), "A")
        self.assertEqual(cat.rank_of("S&P"), "A")

    def test_abbreviation_matches_inside_a_longer_venue_string(self):
        cat = ccf_mod.CcfCatalog.load()
        found = cat.match("Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition (CVPR)")
        self.assertIsNotNone(found)
        self.assertEqual(found.abbr, "CVPR")

    def test_full_name_outranks_a_multi_word_abbreviation(self):
        """'Journal of Machine Learning Research' is JMLR, not the journal 'Machine Learning'."""
        cat = ccf_mod.CcfCatalog.load()
        self.assertEqual(cat.match("Journal of Machine Learning Research").abbr, "JMLR")
        self.assertEqual(cat.match("Machine Learning").abbr, "Machine Learning")

    def test_an_unknown_venue_is_unmatched_never_guessed(self):
        cat = ccf_mod.CcfCatalog.load()
        self.assertIsNone(cat.match("Journal of Nonexistent Studies"))
        self.assertEqual(cat.rank_of("Some Venue That Does Not Exist"), "")

    def test_a_conference_string_does_not_resolve_to_a_journal_of_the_same_name(self):
        cat = ccf_mod.CcfCatalog.load()
        self.assertIsNone(cat.match("the 2023 Conf on Artificial Intelligence"))
        # The journal of that exact name is still findable by its own name.
        self.assertEqual(cat.match("Artificial Intelligence").kind, "journal")

    def test_catalogue_can_be_replaced_wholesale(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "my.csv"
            path.write_text(
                "abbr,aliases,name,kind,field,rank\n"
                "XYZ,MY ALIAS,My Own Venue,conference,Testing,A\n",
                encoding="utf-8",
            )
            cat = ccf_mod.CcfCatalog.load(path)
            self.assertEqual(cat.rank_of("XYZ"), "A")
            self.assertEqual(cat.rank_of("MY ALIAS"), "A")
            self.assertIsNone(cat.match("NeurIPS"))
            self.assertTrue(cat.verify()["ok"])

    def test_malformed_rows_are_reported_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text(
                "abbr,aliases,name,kind,field,rank\n"
                "AAA,,First Venue,conference,Testing,A\n"
                "AAA,,Duplicate Abbr,conference,Testing,B\n"
                "BBB,,No Rank Venue,conference,Testing,Z\n",
                encoding="utf-8",
            )
            cat = ccf_mod.CcfCatalog.load(path)
            report = cat.verify()
            self.assertFalse(report["ok"])
            self.assertEqual(len(report["duplicates"]), 1)
            # The row with an unparseable rank is dropped rather than defaulted.
            self.assertEqual(len(cat.venues), 2)


class TestTermExtraction(unittest.TestCase):
    def test_phrases_do_not_cross_stopwords(self):
        found = terms_mod.extract_terms("attention is all you need", max_n=2)
        self.assertIn("attention", found)
        self.assertNotIn("attention need", found)

    def test_adjacent_content_words_form_phrases(self):
        found = terms_mod.extract_terms("graph neural networks", max_n=3)
        self.assertIn("graph neural", found)
        self.assertIn("neural network", found)
        self.assertIn("graph neural network", found)

    def test_plurals_fold_but_readable_terms_are_preserved(self):
        self.assertEqual(terms_mod.extract_terms("datasets"), {"dataset"})
        self.assertIn("analysis", terms_mod.extract_terms("analysis"))
        self.assertIn("bias", terms_mod.extract_terms("bias"))

    def test_trailing_punctuation_is_not_part_of_a_term(self):
        found = terms_mod.extract_terms("We study compression. It works.")
        self.assertIn("compression", found)
        self.assertNotIn("compression.", found)

    def test_hyphenated_and_accents_survive(self):
        found = terms_mod.extract_terms("state-of-the-art f1-score")
        self.assertIn("state-of-the-art", found)
        self.assertIn("f1-score", found)

    def test_extraction_is_deterministic(self):
        text = "Graph neural networks for molecular property prediction"
        first = terms_mod.extract_terms(text, max_n=3)
        second = terms_mod.extract_terms(text, max_n=3)
        self.assertEqual(first, second)

    def test_sparse_pairs_find_the_uncombined_concepts(self):
        docs = [
            terms_mod.document_terms(t, _ABSTRACTS[i % len(_ABSTRACTS)])
            for i, t in enumerate(_TITLES)
        ]
        ranked = terms_mod.term_frequencies(docs, top=40, min_docs=2)
        pairs = terms_mod.sparse_pairs(docs, ranked, min_docs=3)
        found = {tuple(sorted(row["terms"])) for row in pairs}
        self.assertIn(("protein", "transformer"), found)
        row = next(r for r in pairs if tuple(sorted(r["terms"])) == ("protein", "transformer"))
        # The abstracts deliberately mention the other cluster, so the two concepts do
        # occasionally co-occur — but well below what independence would predict.
        self.assertLess(row["together"], row["expected"])
        self.assertGreater(row["expected"], 0)
        self.assertGreater(row["deficit"], 0)

    def test_non_sparse_pairs_are_excluded(self):
        """A pair that co-occurs as often as independence predicts is not an opening."""
        docs = [{"alpha", "beta"} for _ in range(10)]
        ranked = [
            {"term": "alpha", "docs": 10},
            {"term": "beta", "docs": 10},
        ]
        self.assertEqual(terms_mod.sparse_pairs(docs, ranked, min_docs=3), [])


class TestGapMining(unittest.TestCase):
    def test_marker_kinds_are_recognised(self):
        cases = {
            "Future work will explore scaling to million node graphs.": "future_work",
            "Few works study interpretability in this setting.": "absence",
            "A key limitation is that the method does not consider large graphs.": "limitation",
            "The approach is computationally expensive on long inputs.": "inefficiency",
            "Our method assumes that structures are static.": "idealization",
        }
        for sentence, kind in cases.items():
            with self.subTest(sentence=sentence):
                self.assertEqual(gaps_mod.gap_kind(sentence), kind)

    def test_a_sentence_with_no_marker_declares_no_gap(self):
        self.assertEqual(gaps_mod.gap_kind("We present a new method for graph learning."), "")

    def test_chinese_markers_are_recognised(self):
        self.assertEqual(
            gaps_mod.gap_kind("未来工作将进一步研究该问题在大规模图上的表现。"),
            "future_work",
        )

    def test_short_fragments_are_not_sentences(self):
        self.assertEqual(gaps_mod.sentences("Short. Also short."), [])

    def test_gap_mining_reports_anchors_not_prose(self):
        with _library() as lib:
            survey = survey_mod.survey(lib, "molecular", offline=True)
            result = gaps_mod.gaps(lib, survey)
            self.assertTrue(result["usable"])
            self.assertTrue(result["declared_gaps"])
            for row in result["declared_gaps"]:
                self.assertTrue(row["work_id"])
                self.assertIn("sentence", row)
                self.assertTrue(row["kind"])
                # Every anchor must resolve to a stored work.
                self.assertIsNotNone(lib.load(row["work_id"]))

    def test_unknown_survey_id_is_an_error_not_an_empty_result(self):
        with _library() as lib:
            result = gaps_mod.gaps(lib, "deadbeefdeadbeef")
            self.assertEqual(result["error"], "unknown_survey")


class TestOperators(unittest.TestCase):
    def test_operator_ids_are_unique_and_stable(self):
        ids = operators_mod.ids()
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 10)
        self.assertEqual(ids, operators_mod.ids())

    def test_every_operator_declares_a_known_novelty_type_and_difficulty(self):
        for op in operators_mod.all_operators():
            with self.subTest(operator=op.id):
                self.assertIn(op.novelty_type, operators_mod.NOVELTY_TYPES)
                self.assertGreaterEqual(op.difficulty, operators_mod._MIN_DIFFICULTY)
                self.assertLessEqual(op.difficulty, operators_mod._MAX_DIFFICULTY)
                self.assertIn(op.ccf_ceiling, rating_mod.BANDS)

    def test_operators_are_selected_by_the_evidence_they_accept(self):
        sparse = {op.id for op in operators_mod.for_evidence("sparse_pair")}
        self.assertIn("recombination", sparse)
        self.assertIn("integrate", sparse)
        self.assertNotIn("boundary", sparse)
        kinds = {op.id for op in operators_mod.for_evidence("limitation")}
        self.assertIn("boundary", kinds)
        self.assertIn("paradox", kinds)
        self.assertNotIn("recombination", kinds)

    def test_unknown_evidence_selects_nothing(self):
        self.assertEqual(operators_mod.for_evidence("not_a_kind"), [])


class TestCandidates(unittest.TestCase):
    def test_candidates_all_carry_an_anchor_and_a_stable_key(self):
        with _library() as lib:
            survey = survey_mod.survey(lib, "molecular", offline=True)
            result = candidates_mod.build(lib, survey)
            self.assertTrue(result["candidates"])
            keys = set()
            for cand in result["candidates"]:
                self.assertTrue(cand["candidate_id"])
                self.assertTrue(cand["dedup_key"])
                keys.add(cand["dedup_key"])
                evidence = cand["evidence"]
                if evidence["type"] == "declared_gap":
                    self.assertTrue(evidence["work_id"])
                    self.assertTrue(evidence["sentence"])
                    self.assertIsNotNone(lib.load(evidence["work_id"]))
                else:
                    self.assertEqual(len(evidence["terms"]), 2)
                    self.assertIn("together", evidence)
            # Keys are unique within a run, so "one at a time" is meaningful.
            self.assertEqual(len(keys), len(result["candidates"]))

    def test_scores_vary_and_are_fully_explained(self):
        with _library() as lib:
            survey = survey_mod.survey(lib, "molecular", offline=True)
            result = candidates_mod.build(lib, survey)
            scores = {c["score"] for c in result["candidates"]}
            self.assertGreater(len(scores), 1)
            for cand in result["candidates"]:
                parts = {b["part"] for b in cand["score_basis"]}
                self.assertEqual(
                    parts, {"directness", "support", "ambition", "novelty"}
                )
                recomputed = round(
                    sum(b["value"] * b["weight"] for b in cand["score_basis"]), 4
                )
                self.assertAlmostEqual(recomputed, cand["score"], places=3)

    def test_building_twice_gives_the_same_ids_and_order(self):
        with _library() as lib:
            survey = survey_mod.survey(lib, "molecular", offline=True)
            first = candidates_mod.build(lib, survey)
            second = candidates_mod.build(lib, survey)
            self.assertEqual(
                [c["candidate_id"] for c in first["candidates"]],
                [c["candidate_id"] for c in second["candidates"]],
            )
            self.assertEqual(
                [c["score"] for c in first["candidates"]],
                [c["score"] for c in second["candidates"]],
            )

    def test_a_committed_key_is_not_proposed_again(self):
        with _library() as lib:
            survey = survey_mod.survey(lib, "molecular", offline=True)
            survey_mod.save_survey(lib, survey)
            first = candidates_mod.build(lib, survey)
            chosen = first["candidates"][0]
            store_mod.remember_topic(
                lib,
                {
                    "topic_id": "t1",
                    "title": chosen["title_hint"],
                    "query": survey["query"],
                    "dedup_keys": [chosen["dedup_key"]],
                },
            )
            second = candidates_mod.build(lib, survey)
            keys = {c["dedup_key"] for c in second["candidates"]}
            self.assertNotIn(chosen["dedup_key"], keys)
            self.assertEqual(second["excluded_as_mined"], 1)

    def test_unknown_survey_id_is_an_error(self):
        with _library() as lib:
            result = candidates_mod.build(lib, "deadbeefdeadbeef")
            self.assertEqual(result["error"], "unknown_survey")


class TestDraftAndRating(unittest.TestCase):
    def _draft_one(self, lib: Library) -> dict:
        survey = survey_mod.survey(lib, "molecular", offline=True)
        survey_mod.save_survey(lib, survey)
        built = candidates_mod.build(lib, survey)
        candidates_mod.save_candidates(lib, built)
        return draft_mod.draft(lib, built["candidates"][0]["candidate_id"])

    def test_draft_has_the_sections_a_paper_needs(self):
        with _library() as lib:
            record = self._draft_one(lib)
            headings = [s["heading"] for s in record["sections"]]
            for needed in (
                "Background and problem",
                "Related work and the gap",
                "Contributions",
                "Expected experiments and datasets",
            ):
                self.assertIn(needed, headings)

    def test_datasets_and_baselines_are_harvested_as_observations(self):
        with _library() as lib:
            record = self._draft_one(lib)
            section = next(s for s in record["sections"] if s["n"] == 6)
            names = {d["name"] for d in section["observed_datasets"]}
            self.assertIn("QM9", names)
            self.assertIn("MD17", names)
            baselines = {b["name"] for b in section["observed_baselines"]}
            self.assertTrue({"SchNet", "DimeNet"} & baselines)
            for row in section["observed_datasets"]:
                self.assertGreaterEqual(row["mentions"], 1)

    def test_every_reference_is_a_work_the_library_holds(self):
        with _library() as lib:
            record = self._draft_one(lib)
            self.assertTrue(record["references"])
            for ref in record["references"]:
                self.assertIsNotNone(lib.load(ref["work_id"]))
                self.assertTrue(ref["title"])

    def test_a_draft_is_persisted_and_readable(self):
        with _library() as lib:
            record = self._draft_one(lib)
            reloaded = store_mod.load_json(lib, "records", record["topic_id"])
            self.assertIsNotNone(reloaded)
            self.assertEqual(reloaded["topic_id"], record["topic_id"])

    def test_unknown_candidate_is_an_error(self):
        with _library() as lib:
            result = draft_mod.draft(lib, "deadbeefdeadbeef")
            self.assertEqual(result["error"], "unknown_candidate")

    def test_rating_is_recomputable_and_deterministic(self):
        with _library() as lib:
            record = self._draft_one(lib)
            first = rating_mod.rate(lib, record)
            second = rating_mod.rate(lib, record)
            self.assertEqual(first["estimated_ccf"], second["estimated_ccf"])
            self.assertEqual(first["confidence"], second["confidence"])
            self.assertEqual(first["steps_down"], second["steps_down"])
            # The band can never exceed the stated upper bound.
            self.assertLessEqual(
                rating_mod.BANDS.index(first["estimated_ccf"]),
                rating_mod.BANDS.index(first["upper_bound"]),
            )
            self.assertTrue(first["basis"])
            self.assertTrue(first["disclaimer"])

    def test_rating_names_every_reason_it_moved_down(self):
        with _library() as lib:
            record = self._draft_one(lib)
            result = rating_mod.rate(lib, record)
            rules = {b["rule"] for b in result["basis"]}
            self.assertIn("operator_ceiling", rules)
            self.assertIn("evidence_directness", rules)
            self.assertIn("corpus_support", rules)
            self.assertGreaterEqual(len(result["risks"]), result["steps_down"])

    def test_an_unknown_target_venue_is_reported_not_assumed(self):
        with _library() as lib:
            record = self._draft_one(lib)
            result = rating_mod.rate(lib, record, target_venue="Journal of Nowhere")
            self.assertEqual(result["target_venue_ccf"], "")
            self.assertTrue(
                any(b["rule"] == "target_venue" and b["value"] == "unmatched"
                    for b in result["basis"])
            )

    def test_a_known_target_venue_caps_the_estimate(self):
        with _library() as lib:
            record = self._draft_one(lib)
            result = rating_mod.rate(lib, record, target_venue="APSEC")
            self.assertEqual(result["target_venue_ccf"], "C")
            self.assertEqual(result["estimated_ccf"], "C")

    def test_rating_is_written_back_onto_the_topic(self):
        with _library() as lib:
            record = self._draft_one(lib)
            rating_mod.rate_and_store(lib, record["topic_id"])
            reloaded = store_mod.load_json(lib, "records", record["topic_id"])
            self.assertIn("rating", reloaded)
            self.assertTrue(reloaded["rating"]["estimated_ccf"])


class TestMarkdownRendering(unittest.TestCase):
    def test_markdown_contains_the_skeleton_and_quotes_its_evidence(self):
        with _library() as lib:
            survey = survey_mod.survey(lib, "molecular", offline=True)
            survey_mod.save_survey(lib, survey)
            built = candidates_mod.build(lib, survey)
            candidates_mod.save_candidates(lib, built)
            record = draft_mod.draft(lib, built["candidates"][0]["candidate_id"])
            rating_mod.rate_and_store(lib, record["topic_id"])
            stored = store_mod.load_json(lib, "records", record["topic_id"])
            md = draft_mod.render_markdown(stored)
            self.assertIn("# ", md)
            self.assertIn("estimated CCF", md)
            self.assertIn("## 1. Background and problem", md)
            self.assertIn("## 9. Evidence appendix", md)
            self.assertIn("```bibtex", md)

    def test_markdown_survives_a_unicode_round_trip(self):
        with _library() as lib:
            survey = survey_mod.survey(lib, "molecular", offline=True)
            survey_mod.save_survey(lib, survey)
            built = candidates_mod.build(lib, survey)
            candidates_mod.save_candidates(lib, built)
            record = draft_mod.draft(lib, built["candidates"][0]["candidate_id"])
            md = draft_mod.render_markdown(record)
            path = store_mod.save_text(lib, "drafts", record["topic_id"], md)
            raw = Path(path).read_bytes()
            self.assertEqual(raw.decode("utf-8"), md)
            self.assertNotIn("\ufffd", raw.decode("utf-8"))


class TestAnchorInvariant(unittest.TestCase):
    """`evidence-anchored-topics`: no claim may exist without something to check it against."""

    def test_no_section_can_carry_an_unanchored_claim(self):
        with _library() as lib:
            survey = survey_mod.survey(lib, "molecular", offline=True)
            survey_mod.save_survey(lib, survey)
            built = candidates_mod.build(lib, survey)
            candidates_mod.save_candidates(lib, built)

            checked = 0
            for cand in built["candidates"][:5]:
                record = draft_mod.draft(lib, cand["candidate_id"])
                self.assertTrue(record["evidence"], "a topic must cite its evidence")
                for section in record["sections"]:
                    for anchor in section["anchors"]:
                        checked += 1
                        if anchor["kind"] == "quotation":
                            self.assertTrue(anchor["work_id"])
                            self.assertTrue(anchor["sentence"])
                            self.assertIsNotNone(
                                lib.load(anchor["work_id"]),
                                "an anchor must resolve to a stored work",
                            )
                        else:
                            self.assertEqual(anchor["kind"], "statistic")
                            self.assertEqual(len(anchor["terms"]), 2)
            self.assertGreater(checked, 0)

    def test_every_quotation_anchor_originates_from_a_declared_gap(self):
        with _library() as lib:
            survey = survey_mod.survey(lib, "molecular", offline=True)
            survey_mod.save_survey(lib, survey)
            built = candidates_mod.build(lib, survey)
            candidates_mod.save_candidates(lib, built)
            record = draft_mod.draft(
                lib,
                next(
                    c["candidate_id"]
                    for c in built["candidates"]
                    if c["evidence"]["type"] == "declared_gap"
                ),
            )
            section = next(s for s in record["sections"] if s["n"] == 2)
            quote = section["anchors"][0]
            self.assertEqual(quote["kind"], "quotation")
            self.assertEqual(quote["sentence"], record["evidence"]["sentence"])
            self.assertEqual(quote["work_id"], record["evidence"]["work_id"])


class TestMcpFace(unittest.TestCase):
    """The MCP face drives the same commands, so it must produce the same records."""

    def test_the_whole_pipeline_is_reachable_through_mcp(self):
        from ccb.mcp_server import McpServer

        with tempfile.TemporaryDirectory() as tmp:
            lib = _make_library(Path(tmp))
            root = lib.root
            lib.close()
            server = McpServer(root)
            try:
                survey = server.call_tool(
                    "ccb_topics_survey",
                    {"query": "molecular", "offline": True, "min_works": 5, "min_fulltext": 0},
                )
                self.assertIn("survey_id", survey)
                survey_id = survey["survey_id"]

                found = server.call_tool("ccb_topics_gaps", {"survey_id": survey_id})
                self.assertTrue(found["usable"])

                built = server.call_tool(
                    "ccb_topics_candidates", {"survey_id": survey_id, "limit": 3}
                )
                self.assertTrue(built["candidates"])

                record = server.call_tool(
                    "ccb_topics_draft",
                    {"candidate_id": built["candidates"][0]["candidate_id"]},
                )
                self.assertTrue(record["sections"])
                self.assertTrue(record["evidence"])

                result = server.call_tool("ccb_topics_rate", {"topic_id": record["topic_id"]})
                self.assertIn(result["estimated_ccf"], rating_mod.BANDS)
                self.assertTrue(result["basis"])

                saved = server.call_tool("ccb_topics_save", {"topic_id": record["topic_id"]})
                self.assertEqual(saved["status"], "committed")
                self.assertTrue(Path(saved["markdown_path"]).exists())

                listed = server.call_tool("ccb_topics_list", {})
                self.assertEqual(listed["count"], 1)

                # A retired combination is not proposed again on the next pass.
                rebuilt = server.call_tool(
                    "ccb_topics_candidates", {"survey_id": survey_id, "limit": 3}
                )
                self.assertGreaterEqual(rebuilt["excluded_as_mined"], 1)
            finally:
                server.close()

    def test_an_unknown_id_is_reported_rather_than_raising(self):
        from ccb.mcp_server import McpServer

        with tempfile.TemporaryDirectory() as tmp:
            lib = _make_library(Path(tmp))
            root = lib.root
            lib.close()
            server = McpServer(root)
            try:
                for tool, key in (
                    ("ccb_topics_gaps", "survey_id"),
                    ("ccb_topics_draft", "candidate_id"),
                    ("ccb_topics_rate", "topic_id"),
                    ("ccb_topics_save", "topic_id"),
                ):
                    with self.subTest(tool=tool):
                        out = server.call_tool(tool, {key: "deadbeefdeadbeef"})
                        self.assertTrue(out.get("error"), f"{tool} should report an error")
            finally:
                server.close()


class TestCoverageScopeAndHonesty(unittest.TestCase):
    """Novelty/coverage must describe one population, and must not invent a zero."""

    def test_coverage_counts_within_the_direction_and_the_library_separately(self):
        with _library() as lib:
            wid = lib.all_work_ids()[0]
            corpus = [(wid, "transformer molecular something")]
            cov = candidates_mod._local_coverage(lib, ["transformer"], corpus=corpus)
            self.assertEqual(cov["scope"], "direction")
            self.assertTrue(cov["checked"])
            # The numerator and the denominator are the same population...
            self.assertEqual(cov["hits"], 1)
            self.assertEqual(cov["of"], 1)
            # ...while the whole-library reading list stays a separate, labelled number.
            self.assertGreater(cov["library_hits"], 1)

    def test_hits_can_never_exceed_the_direction_size(self):
        """The old numerator was whole-library and the denominator the direction's, so a
        small survey over a large library reported things like "50 of 25"."""
        with _library() as lib:
            survey = survey_mod.survey(lib, "molecular", offline=True)
            result = candidates_mod.build(lib, survey)
            total = int(survey["corpus"]["works"])
            for cand in result["candidates"]:
                cov = cand["local_coverage"]
                self.assertLessEqual(cov["hits"], cov["of"])
                self.assertEqual(cov["of"], total)

    def test_no_terms_means_not_measured_not_zero(self):
        with _library() as lib:
            cov = candidates_mod._local_coverage(lib, [], corpus=[])
            self.assertFalse(cov["checked"])
            self.assertIn("not measured", cov["note"])

    def test_no_self_check_omits_the_novelty_part_instead_of_faking_it(self):
        with _library() as lib:
            survey = survey_mod.survey(lib, "molecular", offline=True)
            result = candidates_mod.build(lib, survey, self_check=False)
            self.assertTrue(result["candidates"])
            for cand in result["candidates"]:
                self.assertEqual(cand["score_scope"], "no-self-check")
                self.assertFalse(cand["local_coverage"]["checked"])
                novelty = [b for b in cand["score_basis"] if b["part"] == "novelty"][0]
                self.assertIsNone(novelty["value"])
                measured = [b for b in cand["score_basis"] if b["value"] is not None]
                self.assertLess(len(measured), len(cand["score_basis"]))

    def test_an_unmeasured_part_is_renormalised_not_scored_as_zero(self):
        score, basis = candidates_mod._score(
            directness=1.0, support=2, difficulty=3, novelty_hits=None, corpus_size=10
        )
        measured = [b for b in basis if b["value"] is not None]
        remainder = sum(b["weight"] for b in measured)
        self.assertAlmostEqual(
            sum(b["value"] * b["weight"] for b in measured) / remainder, score, places=3
        )

    def test_two_sentences_on_one_page_are_two_gaps(self):
        base = {"type": "declared_gap", "kind": "limitation", "work_id": "arxiv:1",
                "page": 9}
        first = candidates_mod._evidence_key({**base, "sentence": "only considers X"})
        second = candidates_mod._evidence_key({**base, "sentence": "cannot handle Y"})
        self.assertNotEqual(first, second, "one id for two gaps overwrites a record")
        self.assertEqual(
            first,
            candidates_mod._evidence_key({**base, "sentence": "  Only Considers X "}),
            "the key must be stable across case and whitespace",
        )

    def test_rating_skips_coverage_it_could_not_measure(self):
        record = {
            "topic_id": "t1",
            "operator": {"id": "transfer", "difficulty": 2, "ccf_ceiling": "C",
                         "novelty_type": "application"},
            "context": {"directness": 1.0, "support": 3, "corpus_works": 10,
                        "local_coverage_hits": 0, "local_coverage_checked": False},
        }
        out = rating_mod.rate(self._lib, record)
        entry = [b for b in out["basis"] if b["rule"] == "local_coverage"][0]
        self.assertTrue(entry["skipped"])
        self.assertIsNone(entry["value"])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._lib = _make_library(Path(self._tmp.name))

    def tearDown(self):
        self._lib.close()
        self._tmp.cleanup()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
