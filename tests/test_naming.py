"""The rename is total, and this is what keeps it that way.

The project is at a stage where no compatibility is kept: there is no `lit` package to
import, no `LIT_*` environment variable, and no alias module. That is a deliberate
choice, and the failure mode of getting it half-done is quiet — a stale import or an
environment variable read in one file and written in another only shows up when someone
follows documentation that no longer matches the code.

The scan is token-anchored, because `split_pages`, `quality`, `literature` and
`liteparse` all contain the old name as a substring and must survive untouched.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OLD = "l" + "it"                       # never spelled out here, or the scan finds itself
OLD_ENV = "L" + "IT_"
TOKEN = re.compile(rf"(?<![A-Za-z_]){OLD}(?![A-Za-z_])")

SKIP_DIRS = {".git", "papers", "__pycache__", ".mypy_cache", ".pytest_cache",
             ".ruff_cache", ".venv", "venv",
             # User research data: these files naturally contain "lit" (literature,
             # URLs, paper content). They are data, not source code.
             "用户文档", "notes"}
TEXT_SUFFIXES = {".py", ".md", ".html", ".toml", ".txt", ".yaml", ".yml", ".csv"}

# A line may name the old token in order to forbid it or to *describe the rename* —
# a changelog that cannot say what something used to be called cannot explain the change.
# The exemption is line-scoped so the rest of the same file is still checked for stale
# paths and package names.
FORBID_CLAUSE = re.compile(
    r"不要新增|[Nn]ever add|no compatibility|没有兼容层|零兼容|全量改名|曾用名|历史快照"
    r"|[Rr]enamed|改名"
)


def _files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(ROOT).parts
        if any(p in SKIP_DIRS for p in parts):
            continue
        if path.name == Path(__file__).name:      # this file names the old token on purpose
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in (".gitignore",
                                                                 ".gitattributes"):
            yield path


class TestNoOldNameRemains(unittest.TestCase):
    def test_the_package_imports_under_the_new_name(self):
        import ccb  # noqa: F401

        self.assertTrue(hasattr(ccb, "__version__"))

    def test_the_old_package_is_gone(self):
        with self.assertRaises(ModuleNotFoundError):
            __import__(OLD)

    def test_the_source_tree_is_renamed(self):
        self.assertFalse((ROOT / "src" / OLD).exists(), "src/ still holds the old package")
        self.assertTrue((ROOT / "src" / "ccb" / "cli" / "__init__.py").exists(),
                        "the CLI entry package was not renamed")
        self.assertTrue((ROOT / "ccb.py").exists(), "the entry point was not renamed")
        self.assertTrue((ROOT / "ccb-mcp.py").exists())

    def test_no_compatibility_aliases_survive(self):
        """The pre-split import aliases went with the rename; nothing pretends otherwise."""
        for stale in ("model", "ids", "util", "extract", "evidence", "passages", "cite",
                      "net", "resolver", "workindex"):
            with self.subTest(module=stale):
                self.assertFalse(
                    (ROOT / "src" / "ccb" / f"{stale}.py").exists(),
                    f"ccb/{stale}.py is a compatibility alias; the project keeps none",
                )
        self.assertFalse((ROOT / "src" / "ccb" / "channels").exists())

    def test_no_source_file_mentions_the_old_token(self):
        offenders: list[str] = []
        for path in _files():
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.split("\n"), 1):
                if FORBID_CLAUSE.search(line):
                    continue
                if TOKEN.search(line) or OLD_ENV in line:
                    offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()[:90]}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_the_trap_words_survived(self):
        """A substring replace would have destroyed these; the scan must not either."""
        corpus = "\n".join(
            p.read_text(encoding="utf-8", errors="replace") for p in _files()
        )
        for word in ("split_pages", "literature", "quality", "liteparse"):
            with self.subTest(word=word):
                self.assertIn(word, corpus)


class TestVersionIsDeclaredOnce(unittest.TestCase):
    """The release number is typed in one place; everywhere else derives from it.

    It used to be typed in three — pyproject, the package, and the skill metadata — and
    agreed by luck. pyproject now reads the package's value, and this test holds the skill
    to it, because a skill that advertises the wrong version is documentation drift of the
    kind this whole test file exists to catch.
    """

    def test_the_skill_metadata_matches_the_package(self):
        import ccb

        skill = ROOT / ".dsh" / "skills" / "ccb" / "SKILL.md"
        # The version lives under `metadata:` in the frontmatter, hence the indent.
        match = re.search(r'^\s+version:\s*"([^"]+)"', skill.read_text(encoding="utf-8"),
                          re.M)
        self.assertIsNotNone(match, "the skill frontmatter declares no version")
        self.assertEqual(match.group(1), ccb.__version__)

    def test_the_skill_name_matches_the_directory(self):
        skill = ROOT / ".dsh" / "skills" / "ccb" / "SKILL.md"
        match = re.search(r'^name:\s*"?([^"\s]+)"?', skill.read_text(encoding="utf-8"), re.M)
        self.assertIsNotNone(match, "the skill frontmatter declares no name")
        self.assertEqual(match.group(1), "ccb", "DSH discovers skills by directory name")
        self.assertEqual(skill.parent.name, "ccb")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
