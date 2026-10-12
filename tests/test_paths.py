"""Where the workspace is, and what a brand-new one does.

The tool's premise is "clone it and use it": the corpus belongs in the directory the
user cloned. That makes the library-root resolution load-bearing, and its failure mode
*silent* — a working-directory-relative default does not raise, it just scatters
libraries into whatever directory the caller happened to be in, and leaves the clone
empty. So the resolution order is pinned here rather than left to convention.

The second half covers the first thing a new user actually meets: an empty library.
It is the designed starting state (the corpus is local data and is never shipped), so
"empty" must read as normal, not as damage.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ccb.cli import CommandError, _not_found, cmd_extract  # noqa: E402
from ccb.core import paths as core_paths  # noqa: E402
from ccb.core.model import ChannelRecord, Manifestation  # noqa: E402
from ccb.library import store as library_store  # noqa: E402
from ccb.library import Library  # noqa: E402


class _EnvIsolated(unittest.TestCase):
    """Neither resolution test may inherit a real CCB_HOME/CCB_REPO."""

    def setUp(self):
        self._saved = {
            name: os.environ.pop(name, None) for name in ("CCB_HOME", "CCB_REPO")
        }

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class TestLibraryRootResolution(_EnvIsolated):
    def test_default_root_is_the_checkout(self):
        self.assertEqual(
            library_store.default_library_root(),
            ROOT / library_store.DEFAULT_LIBRARY_DIRNAME,
        )

    def test_the_working_directory_does_not_decide(self):
        """A cwd argument may only ever supply the last-resort base."""
        elsewhere = Path(tempfile.gettempdir()) / "ccb-not-a-checkout"
        self.assertEqual(
            library_store.default_library_root(cwd=elsewhere),
            ROOT / library_store.DEFAULT_LIBRARY_DIRNAME,
            "the checkout wins over the working directory",
        )

    def test_ccb_home_wins_outright(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CCB_HOME"] = tmp
            # An explicit root is used verbatim — no directory name appended, because
            # the caller named the directory, not its parent.
            self.assertEqual(library_store.default_library_root(), Path(tmp))

    def test_ccb_repo_wins_over_the_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CCB_REPO"] = tmp
            self.assertEqual(
                library_store.default_library_root(),
                Path(tmp) / library_store.DEFAULT_LIBRARY_DIRNAME,
            )

    def test_installed_package_falls_back_to_the_working_directory(self):
        """No checkout to anchor to -> cwd, rather than a write into site-packages."""
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(library_store, "checkout_root", return_value=None):
                self.assertEqual(
                    library_store.default_library_root(cwd=Path(tmp)),
                    Path(tmp) / library_store.DEFAULT_LIBRARY_DIRNAME,
                )

    def test_the_directory_name_is_visible_and_stable(self):
        name = library_store.DEFAULT_LIBRARY_DIRNAME
        self.assertEqual(name, "papers")
        self.assertFalse(
            name.startswith("."),
            "the workspace must not be a hidden directory: the user has to see it",
        )


class TestCheckoutDetection(_EnvIsolated):
    def test_the_repository_is_recognised(self):
        self.assertTrue(core_paths.looks_like_checkout(ROOT))
        self.assertEqual(core_paths.checkout_root(), ROOT)

    def test_detection_walks_up_from_a_nested_module(self):
        self.assertEqual(
            core_paths.checkout_root(ROOT / "src" / "ccb" / "core" / "paths.py"), ROOT
        )

    def test_a_subdirectory_is_not_a_checkout(self):
        self.assertFalse(core_paths.looks_like_checkout(ROOT / "src"))

    def test_an_installed_layout_is_not_a_checkout(self):
        """`src/ccb/cli.py` alone is a package, not a clone: the entry point is the tell."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "src" / "ccb").mkdir(parents=True)
            (Path(tmp) / "src" / "ccb" / "cli.py").write_text("", encoding="utf-8")
            self.assertIsNone(core_paths.checkout_root(tmp))


class TestFreshWorkspace(_EnvIsolated):
    """An empty library is the documented starting state, so it must not read as broken."""

    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-fresh-"))
        self.lib = Library(self.tmp / "papers")

    def tearDown(self):
        self.lib.close()
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_empty_library_is_not_reported_as_drift(self):
        report = self.lib.self_check(repair=False)
        self.assertEqual(report["problems"], [])
        self.assertTrue(report["index_ok"])
        self.assertIn("index_note", report)

    def test_missing_index_with_works_is_still_drift(self):
        """The empty-library allowance must not weaken real drift detection."""
        self.lib.ensure()
        self.lib.upsert_record(
            ChannelRecord(
                channel="manual",
                title="Attention Is All You Need",
                authors=["Ashish Vaswani"],
                year=2017,
                doi="10.1000/fresh.1",
            )
        )
        self.lib.close()
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(self.lib.index_path) + suffix)
            if p.exists():
                p.unlink()
        report = self.lib.self_check(repair=False)
        kinds = [p["kind"] for p in report["problems"]]
        self.assertIn("index_stale", kinds)

    def test_a_missing_paper_says_the_library_is_empty(self):
        err = _not_found(SimpleNamespace(library=self.lib), "arxiv:1706.03762")
        self.assertEqual(err.code, 3)
        self.assertIn("empty", err.message)
        self.assertIn("ccb find", err.message)

    def test_a_missing_paper_in_a_populated_library_reads_differently(self):
        self.lib.ensure()
        self.lib.upsert_record(
            ChannelRecord(
                channel="manual",
                title="Some Other Paper",
                authors=["B Two"],
                year=2020,
                doi="10.1000/fresh.2",
            )
        )
        err = _not_found(SimpleNamespace(library=self.lib), "arxiv:1706.03762")
        self.assertNotIn("empty", err.message)

    def test_extract_says_which_command_fixes_a_vanished_pdf(self):
        """`has_pdf` reads the record; a deleted file must not reach the extractor."""
        self.lib.ensure()
        upsert = self.lib.upsert_record(
            ChannelRecord(
                channel="manual",
                title="Vanished PDF",
                authors=["C Three"],
                year=2021,
                doi="10.1000/fresh.3",
            )
        )
        work = self.lib.load(upsert.work_id)
        assert work is not None
        work.add_manifestation(
            Manifestation(mid="m1", channel="manual", pdf_path="files/aa/bb.pdf")
        )
        self.lib.save(work)
        self.assertTrue(work.has_pdf(), "the record claims a PDF...")
        self.assertFalse(self.lib.file_abs("files/aa/bb.pdf").exists(), "...that is absent")

        ctx = SimpleNamespace(
            library=self.lib,
            args=SimpleNamespace(identifier=upsert.work_id, engine=""),
        )
        with self.assertRaises(CommandError) as caught:
            cmd_extract(ctx)
        self.assertIn("not there", caught.exception.message)
        self.assertIn("--with-pdf", caught.exception.message)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
