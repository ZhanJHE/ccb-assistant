"""Section detection: the heuristic that turns page-level text into chapter-aware chunks.

Detection is deliberately dumb — known labels, numbered headings, short all-caps lines —
because the failure mode of missing a heading is "the passage has no section" (exactly
the pre-feature behaviour), while the failure mode of a clever-but-wrong detector is a
passage filed under a chapter it does not belong to.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ccb.core.sections import detect_sections  # noqa: E402
from ccb.library.passages import chunk_text  # noqa: E402


class TestDetectSections(unittest.TestCase):
    def test_numbered_headings(self):
        text = (
            "Abstract\nWe study offloading.\n"
            "1. Introduction\nOffloading is old.\n"
            "2.1 Background\nContext matters.\n"
        )
        result = detect_sections(text)
        self.assertEqual(
            [label for _, label in result],
            ["abstract", "introduction", "background"],
        )
        self.assertEqual(result[0][0], 0, "the abstract starts the document")
        self.assertTrue(
            all(a[0] < b[0] for a, b in zip(result, result[1:])),
            "offsets must be ordered so 'last heading before X' is well defined",
        )

    def test_bare_and_uppercase_labels(self):
        text = "RELATED WORK\nPrior systems exist.\n\nMethods\nWe chunk.\n"
        labels = [label for _, label in detect_sections(text)]
        self.assertEqual(labels, ["related work", "methods"])

    def test_chinese_labels(self):
        text = "摘要\n本文提出……\n3 结论\n离线可用。\n"
        self.assertEqual(
            [label for _, label in detect_sections(text)], ["摘要", "结论"]
        )

    def test_ordinary_prose_is_not_a_heading(self):
        text = (
            "The introduction of the method happens here, and the sentence is long "
            "enough that no line looks like a standalone label.\n"
            "Results were strong. 42 participants completed the study.\n"
        )
        self.assertEqual(detect_sections(text), [])

    def test_references_is_detected(self):
        self.assertEqual([label for _, label in detect_sections("References\n[1] ...")],
                         ["references"])


class TestChunksCarrySections(unittest.TestCase):
    def test_chunks_inherit_the_last_heading(self):
        text = (
            "1. Introduction\n" + "intro sentence. " * 60 + "\f"
            "still the introduction, on the next page.\n"
            "2. Methods\n" + "method sentence. " * 60
        )
        chunks = chunk_text(text, work_id="x")
        self.assertTrue(chunks, "a sized text must produce chunks")
        first = [c for c in chunks if c.section == "introduction"]
        methods = [c for c in chunks if c.section == "methods"]
        self.assertTrue(first, "chunks before the second heading are introduction")
        self.assertTrue(methods, "chunks after it are methods")
        self.assertLess(min(c.page for c in methods), 99)

    def test_a_page_without_headings_inherits(self):
        text = "2. Methods\n" + "sentence one. " * 80 + "\f" + "sentence two. " * 40
        chunks = chunk_text(text, work_id="x")
        self.assertTrue(chunks)
        self.assertTrue(all(c.section == "methods" for c in chunks),
                        "the second page has no heading of its own")

    def test_undetected_text_leaves_the_section_empty(self):
        chunks = chunk_text("no headings at all here. " * 40, work_id="x")
        self.assertTrue(chunks)
        self.assertTrue(all(c.section == "" for c in chunks))

    def test_section_round_trips_through_the_passage_payload(self):
        text = "1. Introduction\n" + "sentence. " * 100
        chunk = chunk_text(text, work_id="x")[0]
        restored = type(chunk).from_dict(chunk.as_dict())
        self.assertEqual(restored.section, "introduction")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
