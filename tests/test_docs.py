"""The agent-facing documentation must not drift from the tool it documents.

`docs/for-agents.md` tells an agent what the MCP face costs in context. That number is
measured, not guessed — and because tool schemas change with every parameter, the test
recomputes it and fails when the page goes stale. A stale number is worse than none: an
agent that budgets with it budgets with a lie.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ccb.mcp_server import tool_definitions  # noqa: E402

DOC = ROOT / "开发文档" / "for-agents.md"


class TestForAgentsDoc(unittest.TestCase):
    def test_the_doc_exists_and_is_reachable(self):
        self.assertTrue(DOC.exists(), "for-agents.md is the agent's front door")
        skill = (ROOT / ".dsh" / "skills" / "ccb" / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("for-agents", skill, "the skill must point agents at it")
        self.assertIn("for-agents", readme, "so must the README")

    def test_the_documented_schema_size_matches_reality(self):
        chars = len(json.dumps(tool_definitions(), ensure_ascii=False, sort_keys=True))
        stated = re.search(r"(\d[\d,]*) characters of schema JSON",
                           DOC.read_text(encoding="utf-8"))
        self.assertIsNotNone(
            stated, "for-agents.md must state the schema size in characters"
        )
        self.assertEqual(
            int(stated.group(1).replace(",", "")), chars,
            "the documented MCP context cost is stale — re-measure and update the doc",
        )

    def test_the_two_faces_are_both_described(self):
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("ccb.py", text)
        self.assertIn("ccb-mcp.py", text)
        self.assertIn("contract", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
