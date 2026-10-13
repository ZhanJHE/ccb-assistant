import sys, json
sys.path.insert(0, "src"); sys.path.insert(0, "tests")
from pathlib import Path
import tempfile, shutil
from test_cli import _LibraryFixture, leaf_commands
from ccb.cli._parser import build_parser
from ccb.ops import OPERATIONS

# Build the fixture state once
fx = _LibraryFixture()
fx.setUp()

paths = {}
for op in OPERATIONS:
    paths[tuple((op.path or op.name).split())] = op

results = {}
for leaf in leaf_commands(build_parser()):
    code, out, err = fx.run_cli(["--offline", *leaf])
    keys = []
    if out.strip():
        try:
            d = json.loads(out)
            keys = sorted(d.keys()) if isinstance(d, dict) else ["<non-dict>"]
        except Exception:
            keys = ["<unparseable>"]
    results[tuple(leaf)] = (code, keys)

for leaf in sorted(results):
    code, keys = results[leaf]
    op = paths.get(leaf)
    name = op.name if op else "?"
    print(f"{name:16} {' '.join(leaf):34} rc={code} {keys}")
fx.tearDown()
