"""`core` claims to be a shared floor; this test makes the claim precise.

The old docstring said core knew nothing about disk or network — while `core/util.py`
held the atomic file writers, `os`, and `tempfile`. The floor is now split by content:
`ids` / `model` / `util` are pure computation, and everything that touches a file is
declared as doing so (`files` for the on-disk formats, `extract` for PDFs, `paths` for
checkout probing).

Declared in a test rather than in a docstring, because a claim in a docstring is not a
boundary. The set is explicit instead of inferred from the directory layout, so the rule
survives a file moving without silently stopping to apply.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

# The modules that must stay pure, and the ones allowed to touch the world.
PURE = ("ids", "model", "util")
IMPURE = ("files", "extract", "paths")

FORBIDDEN_ROOTS = {"os", "pathlib", "io", "tempfile", "subprocess", "shutil", "socket",
                   "ssl", "urllib", "importlib", "pickle", "sqlite3"}


def _imported_roots(tree: ast.Module) -> list[str]:
    """Every module an import statement can reach, including deferred ones."""
    roots: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.module:          # `from .files import x`
                roots.append(node.module.split(".")[0])
            elif node.level:                        # `from . import files`
                roots.extend(alias.name for alias in node.names)
            else:
                roots.append(node.module.split(".")[0])
    return roots


def _calls(tree: ast.Module) -> list[str]:
    return [node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]


class TestCorePurity(unittest.TestCase):
    def test_pure_modules_import_nothing_that_touches_the_world(self):
        for name in PURE:
            path = SRC / "ccb" / "core" / f"{name}.py"
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            roots = _imported_roots(tree)
            with self.subTest(module=name):
                self.assertEqual(
                    [r for r in roots if r in FORBIDDEN_ROOTS], [],
                    f"core/{name}.py is declared pure but imports an I/O module — move "
                    f"it to core/files.py, core/extract.py or core/paths.py instead",
                )
                self.assertEqual(
                    [r for r in roots if r in IMPURE], [],
                    f"core/{name}.py must not reach for the disk half of core",
                )

    def test_pure_modules_open_no_file(self):
        for name in PURE:
            path = SRC / "ccb" / "core" / f"{name}.py"
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            with self.subTest(module=name):
                self.assertNotIn("open", _calls(tree),
                                 "a pure module has no business opening anything")

    def test_every_core_module_is_classified(self):
        classified = set(PURE) | set(IMPURE)
        present = {p.stem for p in (SRC / "ccb" / "core").glob("*.py")
                   if p.stem not in ("__init__",)}
        self.assertEqual(
            present - classified, set(),
            "a new core module must be declared pure or impure — that is the whole "
            "point of having the declaration",
        )

    def test_the_declared_split_matches_reality(self):
        """A module declared impure must actually touch the world; otherwise the
        declaration is noise."""
        for name in IMPURE:
            path = SRC / "ccb" / "core" / f"{name}.py"
            if not path.exists():
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            roots = _imported_roots(tree)
            with self.subTest(module=name):
                self.assertTrue(
                    bool(set(roots) & FORBIDDEN_ROOTS) or "open" in _calls(tree),
                    f"core/{name}.py is declared impure but imports nothing that "
                    f"touches the world — reclassify it as pure",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
