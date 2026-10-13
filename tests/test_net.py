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


class TestTransportBounds(unittest.TestCase):
    """The promises the transport makes about *how* it waits and what it returns."""

    def setUp(self):
        self.http = Http(default_rps=1000.0)

    def test_retry_after_is_honoured_but_capped(self):
        """A server may ask us to wait; it may not hang the command for an hour."""
        slept: list[float] = []
        hdrs = http.client.HTTPMessage()
        hdrs["Retry-After"] = "3600"

        def failing(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 429, "slow down", hdrs, None)

        with mock.patch("urllib.request.urlopen", side_effect=failing), \
                mock.patch("ccb.search.net.time.sleep", side_effect=slept.append):
            resp = self.http.request("https://x.example/api")
        self.assertEqual(resp.status, 429)
        self.assertTrue(slept, "a 429 with Retry-After should back off between attempts")
        self.assertLessEqual(max(slept), 60.0, "Retry-After must be capped")

    def test_the_declared_charset_is_used_for_decoding(self):
        body = "标题：扩散模型".encode("gbk")
        fake = _fake_response(200, body, {"Content-Type": "application/json; charset=gbk"})
        with mock.patch("urllib.request.urlopen", return_value=fake):
            resp = self.http.request("https://x.example/api")
        self.assertIn("扩散模型", resp.body)

    def test_an_unknown_charset_falls_back_instead_of_raising(self):
        fake = _fake_response(200, b"ok", {"Content-Type": "text/plain; charset=nope-9"})
        with mock.patch("urllib.request.urlopen", return_value=fake):
            resp = self.http.request("https://x.example/api")
        self.assertEqual(resp.body, "ok")

    def test_an_unfetchable_url_returns_a_response_instead_of_raising(self):
        """`Request()` rejects a URL with no scheme; that must not escape as a traceback.

        `urlopen` is stubbed to fail loudly, which also proves the failure is detected
        before any I/O is attempted.
        """
        boom = mock.patch("urllib.request.urlopen", side_effect=AssertionError("no I/O"))
        with boom:
            resp = self.http.request("example.com/no-scheme")
        self.assertEqual(resp.status, 0)
        self.assertIn("not a fetchable URL", resp.error)
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("no I/O")):
            data, dl_resp = self.http.download("example.com/no-scheme")
        self.assertEqual(data, b"")
        self.assertEqual(dl_resp.status, 0)


class TestHostRateLimits(unittest.TestCase):
    """The declared rate must reach the bucket that is keyed by the *host*."""

    def test_declared_rates_are_keyed_by_host(self):
        from ccb.search.channels.registry import Registry

        reg = Registry()
        # arXiv asks for >= 3 seconds between requests; keying the table by channel name
        # meant this silently became the 1 req/s default for every host.
        self.assertAlmostEqual(reg.http._bucket("export.arxiv.org").rate, 0.34, places=3)
        self.assertAlmostEqual(reg.http._bucket("arxiv.org").rate, 0.34, places=3)
        self.assertAlmostEqual(reg.http._bucket("api.crossref.org").rate, 2.0, places=3)
        self.assertAlmostEqual(reg.http._bucket("api.openalex.org").rate, 2.0, places=3)
        self.assertNotIn("arxiv", reg.http.host_rates, "channel names are not hosts")

    def test_every_http_channel_declares_the_hosts_it_requests(self):
        """A channel that forgets `hosts` silently loses its declared rate."""
        import importlib

        from ccb.search.channels.registry import BUILTIN_CHANNELS

        for name, target in BUILTIN_CHANNELS.items():
            mod_name, _, cls_name = target.partition(":")
            module = importlib.import_module(f"ccb.search.channels.{mod_name}")
            cls = getattr(module, cls_name)
            if cls.spec.kind != "http":
                # A local CLI/MCP-backed channel makes no HTTP request of its own.
                continue
            with self.subTest(channel=name):
                self.assertTrue(cls.spec.hosts, f"{name} declares no hosts for its rate")

    def test_a_registry_override_does_not_rewrite_the_class_spec(self):
        """`spec` is a class attribute: an override must not leak into other instances."""
        from ccb.search.channels.registry import Registry
        from ccb.search.channels.arxiv import ArxivChannel

        before = ArxivChannel.spec.rate_rps
        reg = Registry()
        reg._channels["arxiv"].spec.rate_rps = 999.0
        self.assertEqual(ArxivChannel.spec.rate_rps, before)
        self.assertIsNot(reg._channels["arxiv"].spec, ArxivChannel.spec)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
