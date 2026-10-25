"""Offline Docling classification. No Docker/TrueNAS/network requests."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/truenas/diagnose-docling-readiness.py"
spec = importlib.util.spec_from_file_location("docling_readiness", PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DoclingReadinessTest(unittest.TestCase):
    def test_app_state_absent_ambiguous_and_running(self):
        self.assertEqual(module.app_state([]), "ABSENT")
        self.assertEqual(module.app_state([{"id": "docling", "state": "RUNNING"}]), "RUNNING")
        self.assertEqual(module.app_state([{"id": "docling"}, {"id": "docling"}]), "UNKNOWN")
        self.assertEqual(module.app_state({}), "UNKNOWN")

    def test_all_ready_does_not_claim_ingestion(self):
        def mocked(*args, **kwargs):
            if args[:2] == ("midclt", "call"):
                return True, '[{"id":"docling","state":"RUNNING"}]'
            if args[:2] == ("docker", "inspect"):
                return True, "running\n"
            if args[:2] == ("docker", "exec"):
                return True, ""
            raise AssertionError("Unexpected subprocess")
        with patch.object(module, "command", side_effect=mocked):
            with patch.object(module, "host_ready", return_value="READY"):
                report = module.diagnose()
        self.assertEqual(report["status"], "READY_ONLY")
        self.assertEqual(report["next"], "run_synthetic_pdf_conversion_before_ingestion")

    def test_absent_app_stays_not_ready(self):
        with patch.object(module, "command", return_value=(True, "[]")):
            with patch.object(module, "host_ready", return_value="UNREACHABLE"):
                report = module.diagnose()
        self.assertEqual(report["app"], "ABSENT")
        self.assertEqual(report["status"], "NOT_READY")

    def test_no_raw_http_payload_or_secret_is_printed(self):
        text = PATH.read_text(encoding="utf-8")
        self.assertNotIn("print(payload)", text)
        self.assertNotIn("print(status)", text)
        self.assertIn("NOT_TESTED: PDF_conversion_ingestion_or_retrieval", text)


if __name__ == "__main__":
    unittest.main()
