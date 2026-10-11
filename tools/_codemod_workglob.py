"""Codemod: make every work-file scan match the two-level shard layout.

`work_path_shard` produces `works/<2>/<2>/<id>.json`, but the scans used a one-level
glob (`*/*.json`), so `iter_works()`/`count()`/`stats()`/export silently saw an empty
library while `resolve()` still worked via its own fallback. Centralising the pattern
prevents the two from drifting apart again.

Run from the repo root: python tools/_codemod_workglob.py
"""

from __future__ import annotations

import pathlib
import sys

TARGET = pathlib.Path("src/lit/library.py")
OLD = 'self.works_dir.glob("*/*.json")'
NEW = "self.works_dir.glob(WORK_FILE_GLOB)"
GLOB_DEF = '''
# Every place that enumerates work files uses this one pattern. `work_path_shard`
# shards two levels deep, so a single-level glob would silently report an empty
# library while individual lookups still succeeded.
WORK_FILE_GLOB = "**/*.json"
'''

ANCHOR = 'DEFAULT_LIBRARY_DIRNAME = ".lit"'


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if "WORK_FILE_GLOB" not in text:
        if ANCHOR not in text:
            print(f"anchor not found in {TARGET}")
            return 1
        text = text.replace(ANCHOR, ANCHOR + "\n" + GLOB_DEF.strip(), 1)
    count = text.count(OLD)
    text = text.replace(OLD, NEW)
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"replaced {count} occurrence(s); WORK_FILE_GLOB defined")
    return 0


if __name__ == "__main__":
    sys.exit(main())
