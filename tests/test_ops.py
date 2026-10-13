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
        # `contract` and `install-skill` are entry-layer utilities: they serve the tool
        # as a whole rather than any one module, and say so in the table.
        entry_utilities = {op.name for op in ops.OPERATIONS
                           if not op.group and not op.module}
        unclaimed = {op.path for op in ops.OPERATIONS if not op.group} - claimed
        self.assertEqual(unclaimed, entry_utilities,
                         "a command no module claims is invisible — unless it is an "
                         "entry-layer utility, and there are only those two")
        self.assertEqual(entry_utilities, {"contract", "install-skill"})


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


class TestPromptFace(unittest.TestCase):
    """The MCP prompts surface: the canonical sequences as one-click templates.

    A prompt that cannot say what it used to be called, or that forgets the
    never-answer-from-memory rule, would steer agents around the very invariants the
    tools enforce - so the templates are pinned here, not just their names.
    """

    def _protocol(self, method: str, params=None, mid: int = 1):
        import tempfile

        from ccb.mcp_server import _handle_protocol

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        server = McpServer(Path(tmp.name) / "lib")
        self.addCleanup(server.close)
        msg = {"jsonrpc": "2.0", "id": mid, "method": method}
        if params is not None:
            msg["params"] = params
        return _handle_protocol(msg, server)

    def test_initialize_advertises_the_prompts_capability(self):
        import json

        result = json.loads(
            json.dumps(self._protocol("initialize", {})["result"])
        )
        self.assertIn("prompts", result["capabilities"])

    def test_prompts_list_matches_the_declaration(self):

        prompts = self._protocol("prompts/list", {})["result"]["prompts"]
        self.assertEqual(
            [p["name"] for p in prompts], [p.name for p in ops.PROMPTS]
        )
        for entry, declared in zip(prompts, ops.PROMPTS):
            self.assertEqual(
                [a["name"] for a in entry["arguments"]],
                [a.name for a in declared.arguments],
            )

    def test_prompts_get_renders_every_placeholder(self):

        result = self._protocol(
            "prompts/get",
            {"name": "ccb-literature-review",
             "arguments": {"topic": "SmartNIC offload", "limit": "5"}},
        )["result"]
        text = result["messages"][0]["content"]["text"]
        self.assertIn("SmartNIC offload", text)
        self.assertNotIn("{", text, "a placeholder left behind is a broken template")

    def test_an_unknown_prompt_is_an_invalid_params_error(self):

        response = self._protocol("prompts/get", {"name": "no-such-prompt"})
        self.assertEqual(response["error"]["code"], -32602)  # INVALID_PARAMS

    def test_templates_carry_the_wording_rules(self):
        for prompt in ops.PROMPTS:
            with self.subTest(prompt=prompt.name):
                self.assertIn(
                    "anchor", prompt.template,
                    "every workflow must demand work_id + page anchors",
                )
        review = next(p for p in ops.PROMPTS if p.name == "ccb-literature-review")
        self.assertIn("not-covered", review.template)
        self.assertIn("never fill the gap from memory", review.template)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
