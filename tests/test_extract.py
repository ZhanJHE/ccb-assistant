"""The extraction guard: huge PDFs are stored but not read.

The failure this guards against is a 500-page scanned report stalling `get --with-pdf`
for minutes — the download is fine, the *extraction* is the drag. The PDF is stored
either way (the record stays truthful about what exists); only reading declines, with
the way out named. The limit is an environment variable, so one unusual paper does not
force a code change.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ccb.core.extract import MAX_EXTRACT_BYTES, extract_text  # noqa: E402


def _fake_pdf(size: int) -> Path:
    """A file that passes every earlier check (exists, magic bytes) at `size` bytes."""
    p = Path(os.environ["CCB_TEST_TMP"]) / f"big-{size}.pdf"
    header = b"%PDF-1.4\n"
    p.write_bytes(header + b"\x00" * max(0, size - len(header)))
    return p


class TestExtractionSizeGuard(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp(prefix="ccb-extract-")
        os.environ["CCB_TEST_TMP"] = self.tmp

    def tearDown(self):
        os.environ.pop("CCB_TEST_TMP", None)
        os.environ.pop("CCB_MAX_EXTRACT_BYTES", None)
        for p in Path(self.tmp).glob("*"):
            p.unlink(missing_ok=True)
        os.rmdir(self.tmp)

    def test_over_the_limit_declines_with_the_way_out(self):
        os.environ["CCB_MAX_EXTRACT_BYTES"] = "10"
        result = extract_text(_fake_pdf(400))
        self.assertFalse(result.ok)
        self.assertIn("extraction guard", result.error)
        self.assertIn("CCB_MAX_EXTRACT_BYTES", result.error)

    def test_under_the_limit_reaches_the_engines(self):
        os.environ["CCB_MAX_EXTRACT_BYTES"] = "10"
        result = extract_text(_fake_pdf(5))
        # A 5-byte "pdf" passes the guard and fails later, at the engine step —
        # the guard must not be what stopped it.
        self.assertNotIn("extraction guard", result.error)

    def test_default_limit_is_twenty_megabytes(self):
        self.assertEqual(MAX_EXTRACT_BYTES, 20 * 1024 * 1024)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
