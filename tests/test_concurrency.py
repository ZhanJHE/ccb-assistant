"""Two processes mutating one papers/ directory — the normal agent situation.

A read-modify-write on `library.json` that is not serialized loses updates silently:
one session's paper count or fingerprint simply overwrites the other's. This file holds
the test that would catch that — two real interpreter processes racing upserts against
one library — because an in-process test cannot exercise the cross-process lock.

The lock file (`papers/.lock`) persisting after a run is the steady state, not litter.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ccb.library import Library  # noqa: E402

WORKER = '''\
import sys
sys.path.insert(0, sys.argv[1])
from ccb.library import Library
from ccb.core.model import ChannelRecord

lib = Library(sys.argv[2])
lib.ensure()
tag, n = sys.argv[3], int(sys.argv[4])
for i in range(n):
    lib.upsert_record(ChannelRecord(
        channel="manual",
        title=f"{tag} paper {i}",
        authors=["A One"],
        year=2020,
        doi=f"10.1000/{tag}.{i}",
    ))
lib.close()
print("done", tag)
'''


class TestConcurrentMutation(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-conc-"))
        self.lib_dir = self.tmp / "papers"
        self.worker = self.tmp / "worker.py"
        self.worker.write_text(WORKER, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_two_processes_upserting_one_library_lose_nothing(self):
        procs = [
            subprocess.Popen(
                [sys.executable, str(self.worker), str(ROOT / "src"),
                 str(self.lib_dir), tag, "15"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
            )
            for tag in ("alpha", "beta")
        ]
        results = []
        for p in procs:
            out, err = p.communicate(timeout=120)
            results.append((p.returncode, out, err))

        for (rc, out, err), tag in zip(results, ("alpha", "beta")):
            with self.subTest(worker=tag):
                self.assertEqual(rc, 0, f"worker failed: {err}")

        lib = Library(self.lib_dir)
        try:
            # Neither process's work may overwrite the other's meta: 30 records, and a
            # meta `works` count that agrees with what is on disk. (`work_created` is
            # logged twice per upsert — a pre-existing wart — hence >=, not ==.)
            self.assertEqual(lib.count(), 30)
            self.assertEqual(lib.meta().get("works"), 30)
            self.assertGreaterEqual(lib.count_events("work_created"), 30)
        finally:
            lib.close()

    def test_the_lock_file_is_the_steady_state(self):
        lib = Library(self.lib_dir)
        lib.ensure()
        lib.close()
        self.assertTrue((self.lib_dir / ".lock").exists(),
                        "the lock file persists; it is not litter")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
