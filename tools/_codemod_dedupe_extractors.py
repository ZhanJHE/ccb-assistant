"""Codemod: remove the response-normalising duplicates now provided by the mixin.

`GenericCliChannel` and `GenericMcpChannel` each carried their own copy of the JSON
envelope normaliser, and `GenericMcpChannel` called the CLI class's copy as an *unbound*
method — binding the wrong object to the first parameter and silently shifting every
argument, so MCP-sourced searches returned nothing with no error. Collapsing both onto
one mixin removes the duplication and the failure mode with it.

Run from the repo root: python tools/_codemod_dedupe_extractors.py
"""

from __future__ import annotations

import ast
import pathlib
import sys

TARGET = pathlib.Path("src/lit/channels/generic.py")


def strip_method(source: str, class_name: str, method_name: str) -> str:
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    node = next(
        (n for n in cls.body
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method_name),
        None,
    )
    if node is None:
        return source
    lines = source.splitlines(keepends=True)
    start = node.lineno - 1
    while start > 0 and lines[start - 1].lstrip().startswith("@"):
        start -= 1
    end = node.end_lineno
    while end < len(lines) and not lines[end].strip():
        end += 1
    return "".join(lines[:start] + lines[end:])


def main() -> int:
    src = TARGET.read_text(encoding="utf-8")

    for method in ("_extract", "_map_item"):
        src = strip_method(src, "GenericCliChannel", method)

    # The MCP channel shares the same normaliser instead of borrowing it unbound.
    src = src.replace(
        "class GenericMcpChannel(_DeclaredChannel):",
        "class GenericMcpChannel(_ResponseExtractor, _DeclaredChannel):",
        1,
    )
    src = src.replace(
        "GenericCliChannel._extract(self, data, res, limit=limit, mapping=self.decl.get('map') or {})",
        "self._extract(data, res, limit=limit, mapping=self.decl.get('map') or {})",
    )
    src = src.replace(
        'GenericCliChannel._extract(self, data, res, limit=limit, mapping=self.decl.get("map") or {})',
        'self._extract(data, res, limit=limit, mapping=self.decl.get("map") or {})',
    )
    src = src.replace(
        'GenericCliChannel._extract(self, data, res, limit=5, mapping=self.decl.get("map") or {})',
        'self._extract(data, res, limit=5, mapping=self.decl.get("map") or {})',
    )

    TARGET.write_text(src, encoding="utf-8", newline="\n")

    # Report what remains.
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        names = [n.name for n in cls.body if isinstance(n, ast.FunctionDef)]
        dups = [n for n in names if names.count(n) > 1]
        if dups:
            print(f"WARNING {cls.name} still has duplicates: {dups}")
    remaining = [
        line for line in TARGET.read_text(encoding="utf-8").splitlines()
        if "GenericCliChannel._extract" in line
    ]
    print(f"unbound borrows remaining: {len(remaining)}")
    return 0 if not remaining else 1


if __name__ == "__main__":
    sys.exit(main())
