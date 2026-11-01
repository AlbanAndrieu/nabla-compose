"""Offline HTTP diagnostics contracts: no DNS requests or secrets."""
from __future__ import annotations

import io
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, ProxyHandler
import importlib.util

MODULE = Path(__file__).resolve().parents[1] / 'scripts/lib/http_diagnostics.py'
spec = importlib.util.spec_from_file_location('http_diagnostics', MODULE)
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class Response:
    def __init__(self, status=200, body=b'{}'):
        self.status = status
        self.body = io.BytesIO(body)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.body.close()

    def read(self, limit=-1):
        return self.body.read(limit)


class HttpDiagnosticsTests(unittest.TestCase):
    def test_status_success_and_explicit_rejection(self):
        opener = Mock()
        opener.open.return_value = Response(200)
        self.assertEqual(probe.http_status(opener, 'https://test.invalid/api', timeout=4), 200)
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 4)
        error = HTTPError('https://test.invalid/api', 403, 'PRIVATE', {}, io.BytesIO())
        opener.open.side_effect = error
        self.assertEqual(probe.http_status(opener, 'https://test.invalid/api', timeout=4), 403)
        self.assertTrue(error.fp.closed)

    def test_transport_unknown_never_exposes_exception(self):
        opener = Mock()
        opener.open.side_effect = URLError('SECRET=neverlog')
        self.assertEqual(probe.http_status(opener, 'https://test.invalid', timeout=1), 0)

    def test_invalid_status_not_treated_as_http(self):
        opener = Mock()
        opener.open.return_value = Response('token-secret')
        self.assertEqual(probe.http_status(opener, 'https://test.invalid', timeout=1), 0)

    def test_bounded_json_and_no_raw_secret_on_error(self):
        opener = Mock()
        opener.open.return_value = Response(body=b'{"status":"success"}')
        self.assertEqual(probe.read_json_object(opener, 'https://test.invalid', timeout=5, limit=100), {'status': 'success'})
        opener.open.return_value = Response(body=b'{"value":"SECRET"}')
        with self.assertRaisesRegex(ValueError, 'response too large') as caught:
            probe.read_json_object(opener, 'https://test.invalid', timeout=5, limit=4)
        self.assertNotIn('SECRET', str(caught.exception))

    def test_malformed_json_rejected_without_reflecting_body(self):
        opener = Mock()
        opener.open.return_value = Response(body=b'{"password":"SECRET", malformed')
        with self.assertRaisesRegex(ValueError, 'invalid JSON response') as caught:
            probe.read_json_object(opener, 'https://test.invalid', timeout=5, limit=100)
        self.assertNotIn('SECRET', str(caught.exception))

    def test_json_scalar_and_invalid_limit_are_rejected(self):
        opener = Mock()
        opener.open.return_value = Response(body=b'[1]')
        with self.assertRaisesRegex(ValueError, 'expected JSON object'):
            probe.read_json_object(opener, 'https://test.invalid', timeout=5, limit=100)
        with self.assertRaisesRegex(ValueError, 'invalid response limit'):
            probe.read_json_object(opener, 'https://test.invalid', timeout=5, limit=0)

    def test_redirects_never_follow_to_another_origin(self):
        opener = build_opener(ProxyHandler({}), probe.NoRedirect())
        self.assertTrue(any(isinstance(handler, probe.NoRedirect) for handler in opener.handlers))
        self.assertIsNone(probe.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere.invalid'))

    def test_consumers_import_shared_http_helpers(self):
        root = MODULE.parents[3]
        stack = (root / 'scripts/truenas/diagnose-fastapi-stack.py').read_text(encoding='utf-8')
        prometheus = (root / 'scripts/prometheus/diagnose-failed-scrapes.py').read_text(encoding='utf-8')
        self.assertIn('from scripts.lib.http_diagnostics import', stack)
        self.assertIn('from scripts.lib.http_diagnostics import', prometheus)
        self.assertNotIn('class NoRedirect(', stack)
        self.assertNotIn('class NoRedirect(', prometheus)


if __name__ == '__main__':
    unittest.main()
