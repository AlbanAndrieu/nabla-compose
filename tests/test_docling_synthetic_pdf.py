"""Hermetic acceptance contracts for the bounded Docling synthetic fixture."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "scripts/truenas/smoke-docling-synthetic-pdf.py"
spec = importlib.util.spec_from_file_location("docling_synthetic_pdf", PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeResponse:
    status = 200

    def __init__(self, data=b""):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, n=-1):
        return self.data[:n]


class DoclingSyntheticTest(unittest.TestCase):
    def test_pdf_fixture_is_small_valid_and_contains_sentinel(self):
        fixture = module.synthetic_pdf()
        self.assertTrue(fixture.startswith(b"%PDF-1.4"))
        self.assertTrue(fixture.endswith(b"%%EOF\n"))
        self.assertLess(len(fixture), module.MAX_PDF_BYTES)
        self.assertIn(module.SENTINEL.encode(), fixture)

    def test_multipart_has_exact_local_target_and_synthetic_file(self):
        request = module.multipart_request(module.synthetic_pdf())
        self.assertEqual(request.full_url, "http://172.17.0.24:5001/v1/convert/file")
        self.assertEqual(request.get_method(), "POST")
        self.assertIn(b'name="files"', request.data)
        self.assertIn(b'name="to_formats"', request.data)
        self.assertNotIn(b"/mnt/cpool", request.data)

    def test_no_unapproved_payload_allowed(self):
        with self.assertRaises(ValueError):
            module.multipart_request(b"private")
        with self.assertRaises(ValueError):
            module.multipart_request(b"%PDF-" + b"X" * module.MAX_PDF_BYTES)

    def test_accepts_only_successful_extracted_marker(self):
        good = {"status": "success", "document": {"md_content": module.SENTINEL}}
        self.assertTrue(module.conversion_accepted(json.dumps(good).encode()))
        for item in ({"status": "success", "document": {}},
                     {"status": "failure", "document": {"md_content": module.SENTINEL}},
                     {"status": "success", "document": "not a document"},
                     [good]):
            self.assertFalse(module.conversion_accepted(json.dumps(item).encode()))
        self.assertFalse(module.conversion_accepted(b"invalid json"))
        self.assertFalse(module.conversion_accepted(b"x" * (module.MAX_RESPONSE_BYTES + 1)))

    def test_check_does_not_contact_network(self):
        with patch.object(module, "build_opener", side_effect=AssertionError("network")):
            self.assertEqual(module.main(["--check"]), 0)

    def test_apply_calls_readiness_before_conversion(self):
        class FakeOpener:
            def __init__(self):
                self.targets = []

            def open(self, req, timeout=None):
                target = req if isinstance(req, str) else req.full_url
                self.targets.append(target)
                if target.endswith("/ready"):
                    return FakeResponse()
                payload = {"status": "success", "document": {"md_content": module.SENTINEL}}
                return FakeResponse(json.dumps(payload).encode())

        fake = FakeOpener()
        with patch.object(module, "build_opener", return_value=fake):
            self.assertEqual(module.apply_conversion(), "CONVERSION_PASS")
        self.assertEqual(fake.targets, [module.DOCLING_URL + "/ready",
                                        module.DOCLING_URL + "/v1/convert/file"])

    def test_non_ready_aborts_without_upload(self):
        class NotReady:
            def open(self, _request, timeout=None):
                response = FakeResponse()
                response.status = 503
                return response
        with patch.object(module, "build_opener", return_value=NotReady()):
            self.assertEqual(module.apply_conversion(), "DOC_LING_NOT_READY")

    def test_arg_requires_explicit_mode(self):
        with self.assertRaises(SystemExit):
            module.main([])


if __name__ == "__main__":
    unittest.main()
