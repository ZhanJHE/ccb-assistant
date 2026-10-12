"""Module-boundary tests: the three-module split has to stay a DAG.

The split is only worth having if the boundaries actually hold, and a boundary that
is not tested is a boundary that erodes. These tests parse the real import graph
instead of trusting a convention, so a stray ``from ..search import X`` inside the
library package fails here rather than silently reintroducing the cycles the split
was meant to remove.

Dependency direction, from the inside out::

    core  <-  library  <-  search  <-  topics

``core`` is the shared floor and may import nothing but itself. Each module below a
line may import everything above it. The top-level package (``cli``, ``mcp_server``,
``contract``, the transitional shims) is the entry layer and may import anything.

    python -m unittest discover -s tests
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SRC = ROOT / "src"

# The business modules, in dependency order. A module may always import itself and
# anything listed before it.
ALLOWED: dict[str, set[str]] = {
    "core": {"core"},
    "library": {"core", "library"},
    "search": {"core", "library", "search"},
    "topics": {"core", "library", "search", "topics"},
}

SHIMS = {
    # old path -> canonical path, for the transitional alias files
    "lit.util": "lit.core.util",
    "lit.model": "lit.core.model",
    "lit.ids": "lit.core.ids",
    "lit.extract": "lit.core.extract",
    "lit.evidence": "lit.library.evidence",
    "lit.workindex": "lit.library.index",
    "lit.passages": "lit.library.passages",
    "lit.cite": "lit.library.cite",
    "lit.net": "lit.search.net",
    "lit.resolver": "lit.search.acquire",
}


def _module_name(path: Path) -> str:
    """``src/lit/core/util.py`` -> ``lit.core.util`` (packages lose ``__init__``)."""
    rel = path.relative_to(SRC).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _is_package(path: Path) -> bool:
    return path.name == "__init__.py"


def _resolve(node: ast.ImportFrom, current: str, is_pkg: bool) -> list[str]:
    """Absolute dotted names a ``from ... import ...`` statement can reach."""
    if node.level == 0:
        base = node.module or ""
        return [base] if base else []
    # PEP 328: level 1 is the current package, which for a module is its parent and
    # for a package is itself.
    package = current if is_pkg else current.rpartition(".")[0]
    parts = package.split(".")
    if node.level > 1:
        parts = parts[: -(node.level - 1)]
    base = ".".join(p for p in parts if p)
    if node.module:
        return [f"{base}.{node.module}"]
    # `from . import x` binds submodules of `base`.
    return [f"{base}.{alias.name}" for alias in node.names]


def _imports_of(path: Path) -> list[tuple[str, int]]:
    """Every module imported by ``path``, including deferred (in-function) imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    current = _module_name(path)
    is_pkg = _is_package(path)
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for target in _resolve(node, current, is_pkg):
                found.append((target, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, node.lineno))
    return found


def _module_of(dotted: str) -> str | None:
    """The business module a dotted name belongs to, or None for the entry layer."""
    parts = dotted.split(".")
    if len(parts) >= 2 and parts[0] == "lit" and parts[1] in ALLOWED:
        return parts[1]
    return None


def _package_files() -> list[Path]:
    return sorted(p for p in (SRC / "lit").rglob("*.py") if "__pycache__" not in p.parts)


class TestDependencyGraph(unittest.TestCase):
    """The split is a DAG, and this is the test that keeps it one."""

    def test_every_module_file_parses(self):
        for path in _package_files():
            with self.subTest(module=_module_name(path)):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def test_no_module_imports_a_lower_layer(self):
        violations: list[str] = []
        for path in _package_files():
            owner = _module_of(_module_name(path))
            if owner is None:
                continue  # entry layer: unrestricted
            allowed = ALLOWED[owner]
            for target, lineno in _imports_of(path):
                imported = _module_of(target)
                if imported is None or imported in allowed:
                    continue
                violations.append(
                    f"{_module_name(path)}:{lineno} imports {target} "
                    f"({owner} -> {imported} is not allowed)"
                )
        self.assertEqual(violations, [], "\n".join(violations))

    def test_core_imports_nothing_from_its_siblings(self):
        """`core` is the shared floor: no library, no search, no topics, ever."""
        offenders: list[str] = []
        for path in (SRC / "lit" / "core").rglob("*.py"):
            for target, lineno in _imports_of(path):
                if _module_of(target) in {"library", "search", "topics"}:
                    offenders.append(f"{_module_name(path)}:{lineno} -> {target}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_library_does_not_reach_for_the_network_layer(self):
        """The library performs no network I/O, so it must not import `search`."""
        offenders: list[str] = []
        for path in (SRC / "lit" / "library").rglob("*.py"):
            for target, lineno in _imports_of(path):
                if _module_of(target) in {"search", "topics"}:
                    offenders.append(f"{_module_name(path)}:{lineno} -> {target}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_relative_imports_stay_inside_the_package(self):
        """Every relative import must resolve to something under `lit`."""
        offenders: list[str] = []
        for path in _package_files():
            current = _module_name(path)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or not node.level:
                    continue
                for target in _resolve(node, current, _is_package(path)):
                    if not target.startswith("lit"):
                        offenders.append(f"{current}:{node.lineno} -> {target}")
        self.assertEqual(offenders, [], "\n".join(offenders))


class TestCanonicalApi(unittest.TestCase):
    """The canonical import paths exist and are the ones the modules expose."""

    def test_business_modules_are_importable(self):
        import lit.core  # noqa: F401
        import lit.library  # noqa: F401
        import lit.search  # noqa: F401

    def test_core_exposes_the_shared_floor(self):
        from lit.core import model, paths, util
        from lit.core.ids import compute_work_id, parse_identifier  # noqa: F401
        from lit.core.model import ChannelRecord, Manifestation, WorkRecord  # noqa: F401
        from lit.core.paths import checkout_root  # noqa: F401
        from lit.core.util import normalize_doi, utc_now  # noqa: F401

        self.assertTrue(callable(compute_work_id))
        self.assertTrue(callable(parse_identifier))
        self.assertTrue(callable(utc_now))
        self.assertTrue(callable(checkout_root))
        self.assertTrue(hasattr(model, "WorkRecord"))
        self.assertTrue(hasattr(paths, "checkout_root"))
        self.assertTrue(hasattr(util, "normalize_doi"))

    def test_library_exposes_the_corpus_and_retrieval(self):
        from lit.library import Library, WorkIndex, default_library_root  # noqa: F401
        from lit.library.evidence import EvidenceStore  # noqa: F401
        from lit.library.retrieve import ask, extract_into

        self.assertTrue(callable(ask))
        self.assertTrue(callable(extract_into))

    def test_search_exposes_acquisition(self):
        from lit.search import Registry, Resolver
        from lit.search.acquire import AcquireResult, FindResult  # noqa: F401
        from lit.search.net import Http  # noqa: F401

        self.assertTrue(callable(Registry))
        self.assertIsNotNone(Resolver)

    def test_retrieval_implementation_lives_in_the_library_module(self):
        """The Resolver method must be a delegation, not a second implementation."""
        import inspect

        from lit.library.retrieve import ask as library_ask
        from lit.search.acquire import Resolver

        source = inspect.getsource(Resolver.ask)
        self.assertIn("_ask_impl", source)
        self.assertNotIn("PassageIndex", source)
        self.assertEqual(library_ask.__module__, "lit.library.retrieve")


class TestTransitionalShims(unittest.TestCase):
    """Old import paths still work, and they resolve to the *same* objects."""

    def test_shims_alias_the_canonical_modules(self):
        import importlib

        for old, new in SHIMS.items():
            with self.subTest(old=old):
                shim = importlib.import_module(old)
                canonical = importlib.import_module(new)
                self.assertIs(
                    shim,
                    canonical,
                    f"{old} should be the very same module object as {new}",
                )

    def test_channel_submodule_paths_alias_the_search_package(self):
        import lit.channels.base as shim_base
        import lit.search.channels.base as real_base

        self.assertIs(shim_base, real_base)

    def test_public_names_survive_the_shims(self):
        from lit.model import ChannelRecord, WorkRecord  # noqa: F401
        from lit.net import is_bot_challenge  # noqa: F401
        from lit.resolver import Resolver  # noqa: F401
        from lit.util import normalize_doi, utc_now  # noqa: F401

        self.assertTrue(callable(utc_now))
        self.assertTrue(callable(normalize_doi))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
