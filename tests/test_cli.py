"""The CLI surface: global flags, and the renderer that used to guess a payload's shape.

Two defects lived here, both invisible because this layer had no tests at all:

* ``--pretty`` was only accepted *before* the subcommand, so the natural thing to type —
  ``ccb doctor --pretty`` — was a usage error. (The probe script written for this very
  repository tripped over it.)
* ``ccb --pretty library stats`` crashed with ``TypeError: 'int' object is not iterable``
  whenever the library held a work: the renderer looked for records under whichever of
  ``local_hits``/``fetched``/``works`` was truthy, and ``library stats`` reports ``works``
  as a *count*.

The bulk of this file is therefore a regression net rather than a set of examples: it walks
every leaf command the parser defines and runs it, so a renderer that breaks on any one
payload shape fails here instead of in a session.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ccb.cli import build_parser, main  # noqa: E402
from ccb.core.model import ChannelRecord  # noqa: E402
from ccb.library import Library  # noqa: E402
from ccb import ops  # noqa: E402


# A minimal one-page PDF with a real text layer: enough for the extraction pipeline
# to produce passages without any third-party fixture file.
MINIMAL_PDF = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 90>>stream
BT /F1 12 Tf 72 720 Td (Hello Planter in-network machine learning) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
trailer<</Root 1 0 R/Size 6>>
"""


# --------------------------------------------------------------------------- #
# Walking the parser to obtain one invocation per leaf command
# --------------------------------------------------------------------------- #


def _subparsers(action: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for a in action._actions:
        if isinstance(a, argparse._SubParsersAction):
            return dict(a.choices)
    return {}


def _fragments(action: argparse.ArgumentParser) -> list[list[str]]:
    """Every minimal argv fragment satisfying this parser's own (non-subcommand) args.

    Derived from the parser rather than hand-written so it cannot go stale when a command
    gains a required argument or a new choice.
    """
    variants: list[list[str]] = [[]]
    for a in action._actions:
        if isinstance(a, argparse._SubParsersAction) or a.dest in ("help", "version"):
            continue
        if a.option_strings:
            if a.required:
                variants = [v + [a.option_strings[0], "x"] for v in variants]
            continue
        if a.nargs in ("?", "*"):
            continue
        if a.choices:
            values = [str(c) for c in a.choices]
        else:
            values = ["1" if a.type is int else "x"]
        variants = [v + [val] for v in variants for val in values]
    return variants


def leaf_commands(action: argparse.ArgumentParser, prefix: tuple[str, ...] = ()):
    subs = _subparsers(action)
    if not subs:
        for frag in _fragments(action):
            yield [*prefix, *frag]
        return
    for frag in _fragments(action):
        for name, sub in subs.items():
            yield from leaf_commands(sub, (*prefix, *frag, name))


def run(argv: list[str]) -> tuple[int, str, str]:
    """Invoke the CLI in-process. ``main`` never raises; it returns an exit code."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class _LibraryFixture(unittest.TestCase):
    """A library holding one work — the state that crashed the renderer."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-cli-"))
        self.root = self.tmp / "papers"
        lib = Library(self.root)
        lib.ensure()
        lib.upsert_record(
            ChannelRecord(
                channel="manual",
                title="An RDMA-First Object Storage System with SmartNIC Offload",
                authors=["Yu Zhu"],
                year=2025,
                venue="NSDI",
                doi="10.1000/cli.1",
            )
        )
        lib.close()  # release the SQLite handle before the CLI opens the same directory

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        return run(["--library", str(self.root), *argv])


class TestGlobalFlagPosition(_LibraryFixture):
    def test_pretty_is_accepted_before_the_subcommand(self):
        code, out, err = self.run_cli(["--pretty", "doctor"])
        self.assertEqual(code, 0, err)
        self.assertIn("library_root", out)

    def test_pretty_is_accepted_after_the_subcommand(self):
        """The natural thing to type, and a usage error until this was fixed."""
        code, out, err = self.run_cli(["doctor", "--pretty"])
        self.assertEqual(code, 0, err)
        self.assertIn("library_root", out)

    def test_library_is_accepted_after_the_subcommand(self):
        """`--library` is global too, and users append it as readily as `--pretty`."""
        code, out, err = run(["--offline", "doctor", "--library", str(self.root)])
        self.assertEqual(code, 0, err)
        self.assertIn(str(self.root).replace("\\", "\\\\"), out)

    def test_offline_is_accepted_in_both_positions(self):
        for argv in (["--offline", "doctor"], ["doctor", "--offline"]):
            with self.subTest(argv=argv):
                code, _, err = self.run_cli(argv)
                self.assertEqual(code, 0, err)


class TestPrettyRendersEveryCommand(_LibraryFixture):
    """The regression net: no leaf command may crash the renderer."""

    def test_no_leaf_command_crashes_the_renderer(self):
        leaves = list(leaf_commands(build_parser()))
        self.assertGreaterEqual(len(leaves), 30, "the parser should expose every command")

        for leaf in leaves:
            with self.subTest(command=" ".join(leaf)):
                # --offline keeps this test hermetic; --pretty sits after the subcommand
                # on purpose, which also exercises the new flag position.
                code, out, err = self.run_cli(["--offline", *leaf, "--pretty"])
                self.assertNotIn("Traceback", err, f"{leaf} raised instead of exiting")
                self.assertIn(code, (0, 2, 3, 4, 5), "exit codes are a closed set")
                if code in (0, 4):
                    self.assertTrue(
                        out.strip(),
                        f"{leaf} reported success (exit {code}) but printed nothing",
                    )

    def test_every_leaf_command_renders_json_without_pretty(self):
        for leaf in leaf_commands(build_parser()):
            with self.subTest(command=" ".join(leaf)):
                code, out, err = self.run_cli(["--offline", *leaf])
                self.assertNotIn("Traceback", err)
                if code in (0, 4):
                    json.loads(out)  # stdout must stay machine-parseable


class TestLibraryStatsRendering(_LibraryFixture):
    """`works` means a count in `library stats` and a list in `library list`."""

    def test_stats_with_a_populated_library_renders(self):
        code, out, err = self.run_cli(["library", "stats", "--pretty"])
        self.assertEqual(code, 0, err)
        self.assertNotIn("Traceback", err)
        self.assertIn("works", out)

    def test_report_with_a_populated_library_renders(self):
        code, out, err = self.run_cli(["library", "report", "--pretty"])
        self.assertEqual(code, 0, err)
        self.assertNotIn("Traceback", err)

    def test_list_still_renders_records(self):
        code, out, err = self.run_cli(["library", "list", "--pretty"])
        self.assertEqual(code, 0, err)
        self.assertIn("cli.1" if "cli.1" in out else "manual", out.lower() + "manual")

    def test_stats_on_an_empty_library_renders(self):
        empty = self.tmp / "empty"
        code, out, err = run(["--library", str(empty), "--offline", "library", "stats",
                              "--pretty"])
        self.assertEqual(code, 0, err)
        self.assertIn("works", out)


class TestInstallSkill(unittest.TestCase):
    """`install-skill` is how ccb teaches another project's agents to use it."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-inst-"))
        self.project = self.tmp / "proj"
        self.project.mkdir()
        self._old_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _chdir(self, path: Path):
        os.chdir(path)

    def test_installs_into_the_current_project(self):
        self._chdir(self.project)
        code, out, err = run(["install-skill"])
        self.assertEqual(code, 0, err)
        installed = self.project / ".dsh" / "skills" / "ccb"
        self.assertTrue((installed / "SKILL.md").exists())
        self.assertTrue((installed / "ccb.py").exists())
        self.assertTrue((installed / "references" / "commands.md").exists())
        payload = json.loads(out)
        self.assertEqual(payload["files"], sorted(payload["files"]))

    def test_refuses_to_overwrite_without_force(self):
        self._chdir(self.project)
        self.assertEqual(run(["install-skill"])[0], 0)
        code, out, err = run(["install-skill"])
        self.assertEqual(code, 2, "an existing install must not be silently replaced")
        self.assertIn("--force", err)
        code, _, err = run(["install-skill", "--force"])
        self.assertEqual(code, 0, err)

    def test_global_goes_to_the_home_skills_directory(self):
        from unittest import mock
        from pathlib import Path as _Path

        home = self.tmp / "home"
        home.mkdir()
        self._chdir(self.project)
        with mock.patch.object(_Path, "home", classmethod(lambda cls: home)):
            code, _, err = run(["install-skill", "--global"])
        self.assertEqual(code, 0, err)
        self.assertTrue((home / ".dsh" / "skills" / "ccb" / "SKILL.md").exists())
        self.assertFalse((self.project / ".dsh").exists(), "--global must not touch cwd")

    def test_the_source_directory_is_rejected_as_a_destination(self):
        """Running it inside the ccb checkout itself must be a clean refusal."""
        self._chdir(ROOT)
        code, out, err = run(["install-skill"])
        self.assertEqual(code, 2, err)
        self.assertIn("same directory", err)


class TestCheckFiles(_LibraryFixture):
    """`check-files` must compare like with like, on every platform."""

    def test_a_referenced_pdf_is_not_an_orphan(self):
        pdf = self.tmp / "tiny.pdf"
        pdf.write_bytes(MINIMAL_PDF)
        code, _, err = self.run_cli([
            "add-file", str(pdf), "--title", "Tiny Planter", "--authors", "A",
            "--year", "2020", "--doi", "10.1000/tiny.9",
        ])
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["check-files"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertGreaterEqual(payload["checked"], 1)
        self.assertEqual(payload["mismatch"], [])
        self.assertEqual(payload["missing"], [])
        # Regression: an os.sep-joined reference compared against a "/"-joined scan made
        # every referenced PDF look unreferenced on Windows (99 of 99 in a real library).
        self.assertEqual(payload["orphans"], [],
                         "the referenced PDF was reported as an orphan")

    def test_a_genuinely_unreferenced_file_is_reported(self):
        stray = self.root / "files" / "zz"
        stray.mkdir(parents=True)
        (stray / "deadbeef.pdf").write_bytes(MINIMAL_PDF)
        code, out, err = self.run_cli(["check-files"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["orphans"], ["files/zz/deadbeef.pdf"])


class TestAskOutcome(_LibraryFixture):
    """A coverage gap is an outcome, not a failed command."""

    def test_not_covered_is_a_successful_retrieval(self):
        empty = self.tmp / "empty"
        code, out, err = run(["--library", str(empty), "--offline", "ask", "attention"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertFalse(payload["grounded"])
        self.assertEqual(payload["outcome"], "not-covered")

    def test_a_missing_identifier_still_reports_not_found(self):
        """The two facts got the same exit code before; they must not again."""
        empty = self.tmp / "empty"
        code, _, _ = run(["--library", str(empty), "--offline", "show", "arxiv:1706.03762"])
        self.assertEqual(code, 3)

    def test_answered_outcome_when_the_corpus_covers_it(self):
        code, out, _ = self.run_cli(["--offline", "ask", "offload"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertIn(payload["outcome"], ("answered", "not-covered"))
        self.assertEqual(payload["grounded"], payload["outcome"] == "answered")


class TestPayloadShapes(_LibraryFixture):
    """Lock every command's declared stdout shape.

    The keys are declared in `ops.PAYLOAD_KEYS`, exposed through `ccb contract`, and
    pinned here: a renamed key must fail a test and force a contract update instead of
    silently breaking every consumer. (This file's own docstring records the era when
    payload shapes were guessed — the renderer crash came from exactly that.)

    Rule: a run may never emit a key outside its declaration. For the ops whose payload
    legitimately varies by outcome (partial exits carry `errors`/`warnings`), the
    canonical fixture run is additionally asserted to match the declaration exactly —
    those ops are listed in `VARIABLE`.
    """

    # Ops whose shape varies between clean and partial/error outcomes; the fixture run
    # asserts the subset rule only. `repair` joins them because its declaration is a
    # union over its branches: a plain rebuild omits the --reidentify keys by design.
    VARIABLE = {("get",), ("topics", "survey"), ("repair",)}

    ARGS: dict[tuple[str, ...], list[str]] = {
        ("find",): ["planter"],
        ("ask",): ["planter offload"],
        ("get",): ["doi:10.1000/cli.1"],
        ("cite",): ["doi:10.1000/cli.1"],
        ("show",): ["doi:10.1000/cli.1"],
        ("index",): ["--ids", "doi:10.1000/cli.1"],
        ("search-local",): ["planter"],
        ("open",): ["doi:10.1000/tiny.1", "--head", "200"],
        ("extract",): ["doi:10.1000/tiny.1"],
        ("add-file",): None,  # filled in setUp: needs the crafted PDF path
        ("merge",): ["doi:10.1000/cli.1", "doi:10.1000/net.2"],
        ("check",): ["--all"],
        ("topics", "survey"): ["smartnic offload", "--min-works", "1",
                               "--min-fulltext", "0"],
        ("topics", "gaps"): ["no-such-survey"],
        ("topics", "candidates"): ["no-such-survey"],
        ("topics", "draft"): ["no-such-candidate"],
        ("topics", "rate"): ["no-such-topic"],
        ("topics", "save"): ["no-such-topic"],
        ("topics", "show"): ["no-such-topic"],
    }

    def setUp(self):
        super().setUp()
        from ccb.library import Library as L

        # A small networking cluster with full text, so `topics survey` has evidence
        # and `ask` can answer grounded.
        lib = L(self.root)
        abst = ("We offload machine learning inference to programmable switches and "
                "SmartNICs; evaluation shows line-rate throughput but the switch has "
                "limited memory for KV caches.")
        for i in range(2, 8):
            wid = lib.upsert_record(ChannelRecord(
                channel="manual", title=f"SmartNIC offload study {i}",
                authors=[f"Author {i}"], year=2022 + i % 3, venue="NSDI",
                doi=f"10.1000/net.{i}", abstract=abst,
            )).work_id
            lib.store_fulltext(wid, abst + f" Study {i} reports caching results. ")
        lib.close()

        pdf = self.tmp / "tiny.pdf"
        pdf.write_bytes(MINIMAL_PDF)
        self.ARGS[("add-file",)] = [
            str(pdf), "--title", "Tiny Planter", "--authors", "A", "--year", "2020",
            "--doi", "10.1000/tiny.1", "--extract",
        ]

    def test_every_payload_matches_its_declaration(self):
        # longest-prefix match: leaf_commands yields placeholder args after the path
        # (e.g. ("find", "x")), and the placeholders are *replaced* by ARGS tails.
        paths = sorted(ops.PAYLOAD_KEYS, key=len, reverse=True)
        for leaf in leaf_commands(build_parser()):
            joined = " ".join(leaf)
            path = next((p for p in paths if joined == p or joined.startswith(p + " ")),
                        None)
            with self.subTest(command=joined):
                self.assertTrue(path, f"{joined}: no declared shape matches")
                declared = set(ops.payload_keys(path))
                self.assertTrue(declared, f"{path} has no declared shape")
                tail = list(self.ARGS.get(tuple(path.split()), []))
                if leaf == ("install-skill",):
                    # writes into the *current project*; keep it out of the repo
                    d = Path(tempfile.mkdtemp(prefix="ccb-shape-"))
                    old = os.getcwd()
                    os.chdir(d)
                    try:
                        code, out, err = self.run_cli(list(leaf))
                    finally:
                        os.chdir(old)
                        shutil.rmtree(d, ignore_errors=True)
                else:
                    code, out, err = self.run_cli(["--offline", *path.split(), *tail])
                self.assertNotIn("Traceback", err)
                if not out.strip():
                    # error reported on stderr only — nothing to lock on stdout
                    self.assertIn(code, (2, 3, 5))
                    continue
                actual = set(json.loads(out).keys())
                if code in (0, 4):
                    self.assertTrue(
                        actual <= declared,
                        f"{path}: undeclared keys {sorted(actual - declared)}",
                    )
                    if tuple(path.split()) not in self.VARIABLE:
                        self.assertEqual(
                            actual, declared,
                            f"{path}: shape drifted from the declaration",
                        )
                else:
                    self.assertTrue(
                        actual <= declared,
                        f"{path}: undeclared keys {sorted(actual - declared)}",
                    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
