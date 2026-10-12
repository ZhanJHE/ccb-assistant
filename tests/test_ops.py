"""One operation table, three faces, and the tests that hold them together.

Adding an operation used to mean editing five or six places: a CLI subparser, a CLI
handler, an MCP tool name, an MCP ``inputSchema``, a contract name list, and possibly a
``--pretty`` key mapping. Two of those pairs could disagree *silently* — an advertised
tool with no handler, or a contract naming a flag that does not exist — and both
eventually did (see tests/test_contract.py).

Now `ccb.ops` declares the operations and the faces are derived. These tests fail on the
drift itself rather than on its symptom.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ccb import cli, ops  # noqa: E402
from ccb.contract import contract  # noqa: E402
from ccb.mcp_server import McpServer, tool_definitions  # noqa: E402


def _leaf_paths(action: argparse.ArgumentParser, prefix: tuple[str, ...] = ()) -> list[str]:
    """Every command path the parser exposes, e.g. ``library stats``, ``topics gaps``."""
    sub = None
    for a in action._actions:
        if isinstance(a, argparse._SubParsersAction):
            sub = a
            break
    if sub is None:
        return [" ".join(prefix)] if prefix else []
    out: list[str] = []
    for name, child in sub.choices.items():
        out.extend(_leaf_paths(child, (*prefix, name)))
    return out


class TestOperationTable(unittest.TestCase):
    def test_names_are_unique_within_each_group(self):
        seen: set[str] = set()
        for op in ops.OPERATIONS:
            with self.subTest(op=op.path):
                self.assertNotIn(op.path, seen, "duplicate command path")
                seen.add(op.path)

    def test_mcp_tool_names_are_unique(self):
        names = [op.mcp for op in ops.OPERATIONS if op.mcp]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), 16, "the advertised tool count is part of the surface")

    def test_no_operation_is_left_without_a_face(self):
        for op in ops.OPERATIONS:
            with self.subTest(op=op.path):
                self.assertTrue(
                    op.handler or op.mcp,
                    "an operation that neither has a CLI handler nor is exposed over MCP "
                    "is a declaration nobody can reach",
                )


class TestCliFace(unittest.TestCase):
    def test_every_operation_is_reachable_from_the_parser(self):
        declared = {op.path for op in ops.OPERATIONS}
        exposed = set(_leaf_paths(cli.build_parser()))
        self.assertEqual(
            declared - exposed, set(), "declared but not reachable on the CLI"
        )
        self.assertEqual(
            exposed - declared, set(), "reachable on the CLI but not declared"
        )

    def test_every_declared_handler_exists(self):
        for op in ops.OPERATIONS:
            if not op.handler:
                continue
            with self.subTest(op=op.path):
                handler = getattr(cli, op.handler, None)
                self.assertTrue(callable(handler), f"{op.handler} is not a function in cli")

    def test_positional_params_come_before_options_in_declaration(self):
        """argparse is order-sensitive for positionals; the table should read like argv."""
        for op in ops.OPERATIONS:
            # False = positional, True = option; positionals must come first.
            kinds = [bool(p.cli) for p in op.params if not p.mcp_only]
            with self.subTest(op=op.path):
                self.assertEqual(
                    kinds, sorted(kinds),
                    "an option declared before a positional is almost always a mistake",
                )


class TestMcpFace(unittest.TestCase):
    def test_the_advertised_tools_are_exactly_the_declared_ones(self):
        advertised = {t["name"] for t in tool_definitions()}
        declared = {op.mcp for op in ops.OPERATIONS if op.mcp}
        self.assertEqual(advertised, declared)

    def test_every_advertised_tool_resolves_to_a_handler(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = McpServer(Path(tmp) / "lib")
            try:
                for op in ops.OPERATIONS:
                    if not op.mcp:
                        continue
                    with self.subTest(tool=op.mcp):
                        handler = getattr(server, f"_tool_{op.mcp_handler}", None)
                        self.assertTrue(
                            callable(handler),
                            f"{op.mcp} is advertised but _tool_{op.mcp_handler} does not "
                            f"exist: a client would get an error for a listed tool",
                        )
            finally:
                server.close()

    def test_schemas_are_generated_from_the_same_params(self):
        by_name = {t["name"]: t for t in tool_definitions()}
        for op in ops.OPERATIONS:
            if not op.mcp:
                continue
            schema = by_name[op.mcp]["inputSchema"]
            expected = {p.name for p in op.params if not p.cli_only}
            required = {p.name for p in op.params if p.required and not p.cli_only}
            with self.subTest(tool=op.mcp):
                self.assertEqual(set(schema["properties"]), expected)
                self.assertEqual(set(schema.get("required", [])), required)

    def test_every_tool_has_a_description(self):
        for op in ops.OPERATIONS:
            if not op.mcp:
                continue
            with self.subTest(tool=op.mcp):
                self.assertTrue(ops.MCP_DESCRIPTIONS.get(op.mcp, op.summary).strip())


class TestContractFace(unittest.TestCase):
    def test_module_command_lists_are_derived_not_copied(self):
        for module in contract()["modules"]:
            name = module["name"]
            with self.subTest(module=name):
                self.assertEqual(module["cli"], ops.cli_names(name))
                self.assertEqual(module["mcp"], ops.mcp_names(name))

    def test_every_cli_command_is_claimed_by_a_module(self):
        claimed = {name for m in ("core", "library", "search", "topics")
                   for name in ops.cli_names(m)}
        # `contract` is the contract itself: it belongs to no module and says so.
        unclaimed = {op.path for op in ops.OPERATIONS if not op.group} - claimed - {"contract"}
        self.assertEqual(unclaimed, set(), "a command no module claims is invisible")


class TestRecordsKeys(unittest.TestCase):
    def test_declared_record_keys_are_named(self):
        for op in ops.OPERATIONS:
            for key in op.records_key:
                with self.subTest(op=op.path, key=key):
                    self.assertIsInstance(key, str)
                    self.assertTrue(key.strip())

    def test_the_renderer_reads_the_declared_key(self):
        """`--pretty` must find records where the operation says they are, not by guessing."""
        args = argparse.Namespace(command="library", action="list")
        self.assertEqual(cli._record_keys_for(args), ("works",))
        args = argparse.Namespace(command="library", action="stats")
        self.assertEqual(cli._record_keys_for(args), ())
        args = argparse.Namespace(command="find", action=None)
        self.assertEqual(cli._record_keys_for(args), ("local_hits", "fetched"))
        args = argparse.Namespace(command="nonesuch", action=None)
        self.assertEqual(cli._record_keys_for(args), ())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
