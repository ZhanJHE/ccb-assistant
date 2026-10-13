"""The conditional-GET layer: validators learned on one run become cheap re-checks.

`check` re-verifies a whole corpus; without validators that means re-transferring every
body and re-parsing every record for works that have not changed. The transport layer
remembers ETag / Last-Modified per URL, sends them back, and treats a 304 as an answer —
so the politeness lives in the client, not in a per-channel promise.
"""

from __future__ import annotations

import http.client
import json
import shutil
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# The root-level `ccb.py` entry point would otherwise shadow the `ccb` package when
# this module is the first to import it.
from ccb.search.net import Http  # noqa: E402


def _fake_response(status: int, body: bytes = b"", headers=None):
    """Stand-in for the urllib response object (read/status/headers, with-statement)."""
    hdrs = http.client.HTTPMessage()
    for key, value in (headers or {}).items():
        hdrs[key] = value

    class _Raw:
        def read(self):
            return body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    raw = _Raw()
    raw.status = status
    raw.headers = hdrs
    return raw


def _raise_304(req, timeout=None):
    raise urllib.error.HTTPError(
        req.full_url, 304, "Not Modified", http.client.HTTPMessage(), None
    )


class TestConditionalRequests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-net-"))
        self.validators = self.tmp / "http-validators.json"
        self.http = Http(default_rps=1000.0, validators_path=self.validators)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_200_with_validators_persists_them(self):
        fake = _fake_response(200, b'{"ok": 1}', {"ETag": '"v1"'})
        with mock.patch("urllib.request.urlopen", return_value=fake):
            resp = self.http.request("https://x.example/api", conditional=True)
        self.assertEqual(resp.status, 200)
        stored = json.loads(self.validators.read_text(encoding="utf-8"))
        self.assertEqual(stored["https://x.example/api"]["etag"], '"v1"')
        self.assertEqual(stored["https://x.example/api"]["last_modified"], "")

    def test_the_next_conditional_request_sends_the_validator(self):
        fake = _fake_response(200, b'{"ok": 1}', {"ETag": '"v1"'})
        with mock.patch("urllib.request.urlopen", return_value=fake):
            self.http.request("https://x.example/api", conditional=True)

        captured = {}

        def capturing(req, timeout=None):
            captured["headers"] = dict(req.header_items())
            return _fake_response(200, b'{"ok": 1}', {"ETag": '"v1"'})

        with mock.patch("urllib.request.urlopen", side_effect=capturing):
            self.http.request("https://x.example/api", conditional=True)
        self.assertIn("If-none-match", captured["headers"])

    def test_a_304_is_an_answer_not_an_error(self):
        fake = _fake_response(200, b'{"ok": 1}', {"ETag": '"v1"'})
        with mock.patch("urllib.request.urlopen", return_value=fake):
            self.http.request("https://x.example/api", conditional=True)

        with mock.patch("urllib.request.urlopen", side_effect=_raise_304):
            resp = self.http.request("https://x.example/api", conditional=True)
        self.assertEqual(resp.status, 304)
        self.assertEqual(resp.body, "")
        self.assertEqual(self.http.stats.get("not_modified"), 1)

    def test_without_conditional_no_validator_is_sent(self):
        fake = _fake_response(200, b'{"ok": 1}', {"ETag": '"v1"'})
        with mock.patch("urllib.request.urlopen", return_value=fake):
            self.http.request("https://x.example/api", conditional=True)

        captured = {}

        def capturing(req, timeout=None):
            captured["headers"] = dict(req.header_items())
            return _fake_response(200, b'{"ok": 1}')

        with mock.patch("urllib.request.urlopen", side_effect=capturing):
            self.http.request("https://x.example/api")  # not conditional
        self.assertNotIn("If-none-match", captured["headers"])

    def test_post_never_sends_validators_even_when_conditional(self):
        fake = _fake_response(200, b'{"ok": 1}', {"ETag": '"v1"'})
        with mock.patch("urllib.request.urlopen", return_value=fake):
            self.http.request("https://x.example/api", conditional=True)

        captured = {}

        def capturing(req, timeout=None):
            captured["headers"] = dict(req.header_items())
            return _fake_response(200, b"{}")

        with mock.patch("urllib.request.urlopen", side_effect=capturing):
            self.http.request(
                "https://x.example/api", method="POST", data=b"{}", conditional=True
            )
        self.assertNotIn("If-none-match", captured["headers"])

    def test_the_validator_store_is_bounded(self):
        self.http._MAX_VALIDATORS = 50  # shrink the bound so the test stays fast
        counter = {"i": 0}

        def responding(req, timeout=None):
            counter["i"] += 1
            return _fake_response(200, b"{}", {"ETag": f'"e{counter["i"]}"'})

        with mock.patch("urllib.request.urlopen", side_effect=responding):
            for i in range(60):
                self.http.request(f"https://x.example/api/{i}", conditional=True)
        self.assertLessEqual(
            len(json.loads(self.validators.read_text(encoding="utf-8"))), 50
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
