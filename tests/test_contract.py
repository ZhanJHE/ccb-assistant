"""The contract has to be executable, not aspirational.

`lit contract` is the document every prompt tells the agent to trust over its own memory —
"the contract lives in code rather than in prose that drifts". That claim only holds if the
commands it names actually run, and two of them did not:

* ``lit find "<topic>" --json`` — JSON is already the default output; there is no such flag.
* ``lit export --bibtex`` — the format is a *value* (``--format bibtex``), not a flag.

Both failed with a usage error (exit 2), from the one document the agent is instructed to
trust first. These tests walk every workflow step and hold the contract to its word, so a
future edit that renames a flag fails here instead of in an agent's session.

The second test guards the step schema itself: a step is either an executable command or a
piece of work only the agent can do, and a machine consumer that walks every step must be
able to tell the two apart. Two prose steps used to sit in the ``cmd`` field.
"""

from __future__ import annotations

import re
import shlex
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lit.cli import build_parser  # noqa: E402
from lit.contract import STEP_KINDS, contract  # noqa: E402

PLACEHOLDER = "placeholder"


def _argv_for(cmd: str) -> list[str]:
    """Turn a contract command string into argv, substituting its <placeholders>."""
    parts = shlex.split(cmd)
    if parts and parts[0] == "lit":
        parts = parts[1:]
    return [re.sub(r"^<[^>]+>$", PLACEHOLDER, p) for p in parts]


class TestWorkflowSteps(unittest.TestCase):
    def setUp(self):
        self.workflows = contract()["workflows"]
        self.assertTrue(self.workflows, "the contract lists no workflows at all")

    def test_every_step_declares_a_known_kind(self):
        for name, wf in self.workflows.items():
            for step in wf["steps"]:
                with self.subTest(workflow=name, step=step.get("n")):
                    self.assertIn(
                        step.get("kind"),
                        STEP_KINDS,
                        "every step is either a command or agent work; nothing else",
                    )

    def test_a_command_step_holds_a_command_and_a_human_step_does_not(self):
        for name, wf in self.workflows.items():
            for step in wf["steps"]:
                with self.subTest(workflow=name, step=step.get("n")):
                    if step["kind"] == "command":
                        self.assertTrue(step.get("cmd"), "a command step needs a cmd")
                        self.assertNotIn("do", step)
                    else:
                        self.assertTrue(step.get("do"), "a human step needs a 'do'")
                        self.assertNotIn(
                            "cmd",
                            step,
                            "a human step must not sit in a cmd field — a consumer that "
                            "runs every cmd would try to execute a sentence",
                        )

    def test_every_named_command_is_accepted_by_the_cli(self):
        """The whole point: the contract cannot name a flag that does not exist."""
        parser = build_parser()
        checked = 0
        for name, wf in self.workflows.items():
            for step in wf["steps"]:
                if step["kind"] != "command":
                    continue
                argv = _argv_for(step["cmd"])
                checked += 1
                with self.subTest(workflow=name, step=step["n"], cmd=step["cmd"]):
                    try:
                        parser.parse_args(argv)
                    except SystemExit as exc:  # argparse exits 2 on a usage error
                        self.fail(
                            f"{step['cmd']!r} is not accepted by the CLI "
                            f"(argparse exited {exc.code})"
                        )
        self.assertGreaterEqual(checked, 15, "the contract should name real commands")

    def test_steps_are_numbered_in_order_from_one(self):
        for name, wf in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertEqual(
                    [s["n"] for s in wf["steps"]],
                    list(range(1, len(wf["steps"]) + 1)),
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
