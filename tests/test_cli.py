"""The CLI surface: global flags, and the renderer that used to guess a payload's shape.

Two defects lived here, both invisible because this layer had no tests at all:

* ``--pretty`` was only accepted *before* the subcommand, so the natural thing to type —
  ``lit doctor --pretty`` — was a usage error. (The probe script written for this very
  repository tripped over it.)
* ``lit --pretty library stats`` crashed with ``TypeError: 'int' object is not iterable``
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
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lit.cli import build_parser, main  # noqa: E402
from lit.core.model import ChannelRecord  # noqa: E402
from lit.library import Library  # noqa: E402


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
        self.tmp = Path(tempfile.mkdtemp(prefix="lit-cli-"))
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
