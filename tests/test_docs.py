"""Documentation must not drift from the tool it documents.

Two things are held here. `开发文档/for-agents.md` tells an agent what the MCP face costs
in context; that number is measured, not guessed, and because tool schemas change with
every parameter the test recomputes it and fails when the page goes stale. A stale number
is worse than none: an agent that budgets with it budgets with a lie.

The other is the documentation site. `mkdocs.yml` names every page in `nav`, and the
page tree is the only source of truth for the site — so a page that no nav entry names
is invisible to readers, and a nav entry that no page backs is a 404 waiting for the next
build. Both directions are checked here rather than discovered on the published site.
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
SITE = ROOT / "mkdocs.yml"
DOCS = ROOT / "开发文档"

# `- 标题: path/to/page.md` — the only nav form the site uses. Group headings
# (`- 设计:`) carry no target and are skipped by the pattern.
NAV_ENTRY = re.compile(r"^\s*-\s+[^:]+:\s*(\S+\.(?:md|html))\s*$")


def site_pages() -> set[str]:
    """Every publishable page, relative to the docs directory, POSIX-style."""
    return {
        path.relative_to(DOCS).as_posix()
        for path in DOCS.rglob("*")
        if path.is_file() and path.suffix in {".md", ".html"}
    }


def nav_pages() -> set[str]:
    entries: set[str] = set()
    for line in SITE.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = NAV_ENTRY.match(line)
        if match:
            entries.add(match.group(1))
    return entries


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

    def test_the_skill_body_stays_under_the_pruner_threshold(self):
        """DSH trims a `skill` tool result above 8192 *rendered* characters.

        Rendered means the YAML frontmatter is sliced off (that is what the loader does),
        so that is what is measured here. The margin is deliberately small — the point is
        that going over fails in this test rather than silently losing the tail of the
        instructions an agent is supposed to follow.
        """
        raw = (ROOT / ".dsh" / "skills" / "ccb" / "SKILL.md").read_text(encoding="utf-8")
        rendered = re.sub(r"^---\r?\n.*?\r?\n---(?:\r?\n|$)", "", raw, count=1,
                          flags=re.S).strip()
        self.assertTrue(rendered.startswith("#"), "the body should start with a heading")
        self.assertLess(
            len(rendered), 8192,
            "the skill body is over the 8192-character pruner threshold — move bulk "
            "content into references/",
        )


class TestDocSite(unittest.TestCase):
    """The site's navigation and its page tree describe the same set of pages."""

    def test_the_config_builds_from_the_dev_docs(self):
        self.assertTrue(SITE.exists(), "mkdocs.yml is what turns 开发文档/ into a site")
        config = SITE.read_text(encoding="utf-8")
        self.assertIn("docs_dir: 开发文档", config,
                      "the site must build from the docs tree itself, not a copy of it")
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("site/", ignored, "the build output must never be tracked")

    def test_every_page_is_named_by_the_nav(self):
        unlisted = sorted(site_pages() - nav_pages())
        self.assertEqual(
            unlisted, [],
            "these pages build but no nav entry names them, so readers cannot reach "
            "them: " + ", ".join(unlisted),
        )

    def test_every_nav_entry_has_a_page(self):
        missing = sorted(nav_pages() - site_pages())
        self.assertEqual(
            missing, [],
            "these nav entries point at pages that do not exist (the build would 404 "
            "on them): " + ", ".join(missing),
        )

    def test_the_nav_opens_with_the_home_page(self):
        entries = [line for line in SITE.read_text(encoding="utf-8").splitlines()
                   if NAV_ENTRY.match(line)]
        self.assertIn("index.md", entries[0], "the first nav entry is the site root")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
