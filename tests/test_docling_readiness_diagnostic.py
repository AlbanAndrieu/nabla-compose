"""Offline Docling classification. No Docker/TrueNAS/network requests."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

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
                with patch.object(module, "host_probe", return_value="READY"):
                    report = module.diagnose()
        self.assertEqual(report["status"], "READY_ONLY")
        self.assertEqual(report["next"], "run_synthetic_pdf_conversion_before_ingestion")

    def test_deploying_container_is_initializing_not_failed(self):
        def mocked(*args, **kwargs):
            if args[:2] == ("midclt", "call"):
                return True, '[{"id":"docling","state":"DEPLOYING"}]'
            if args[:2] == ("docker", "inspect"):
                template = args[-2]
                if "RestartCount" in template:
                    return True, "1"
                if ".State.Health" in template:
                    return True, "starting"
                return True, "running"
            if args[:2] == ("docker", "exec"):
                return False, ""
            raise AssertionError("Unexpected subprocess")
        with patch.object(module, "command", side_effect=mocked):
            with patch.object(module, "host_ready", return_value="UNREACHABLE"):
                with patch.object(module, "host_probe", return_value="UNREACHABLE"):
                    report = module.diagnose()
        self.assertEqual(report["status"], "INITIALIZING")
        self.assertEqual(report["containerHealth"], "starting")
        self.assertEqual(report["restartCount"], "1")
        self.assertEqual(report["next"], "observe_docling_container_health_without_redeploy")

    def test_unhealthy_deploying_requires_startup_inspection_not_redeploy(self):
        def mocked(*args, **kwargs):
            if args[:2] == ("midclt", "call"):
                return True, '[{"id":"docling","state":"DEPLOYING"}]'
            if args[:2] == ("docker", "inspect"):
                return True, "unhealthy" if ".State.Health" in args[-2] else "running"
            return False, ""
        with patch.object(module, "command", side_effect=mocked):
            with patch.object(module, "host_ready", return_value="UNREACHABLE"):
                with patch.object(module, "host_probe", return_value="UNREACHABLE"):
                    report = module.diagnose()
        self.assertEqual(report["status"], "INITIALIZING")
        self.assertEqual(report["containerHealth"], "unhealthy")
        self.assertEqual(report["hostLiveness"], "UNREACHABLE")
        self.assertEqual(report["next"], "inspect_docling_startup_without_redeploy")


    def test_running_app_with_unready_api_does_not_pass(self):
        def mocked(*args, **kwargs):
            if args[:2] == ("midclt", "call"):
                return True, '[{"id":"docling","state":"RUNNING"}]'
            if args[:2] == ("docker", "inspect"):
                return True, "running"
            return False, ""
        with patch.object(module, "command", side_effect=mocked):
            with patch.object(module, "host_ready", return_value="UNREACHABLE"):
                with patch.object(module, "host_probe", return_value="UNREACHABLE"):
                    report = module.diagnose()
        self.assertEqual(report["status"], "UNVERIFIED")
        self.assertNotEqual(report["status"], "READY_ONLY")

    def test_absent_app_stays_not_ready(self):
        with patch.object(module, "command", return_value=(True, "[]")):
            with patch.object(module, "host_ready", return_value="UNREACHABLE"):
                with patch.object(module, "host_probe", return_value="UNREACHABLE"):
                    report = module.diagnose()
        self.assertEqual(report["app"], "ABSENT")
        self.assertEqual(report["status"], "NOT_READY")

    def test_no_raw_http_payload_or_secret_is_printed(self):
        text = PATH.read_text(encoding="utf-8")
        self.assertNotIn("print(payload)", text)
        self.assertNotIn("print(status)", text)
        self.assertIn("NOT_TESTED: PDF_conversion_ingestion_or_retrieval", text)
        self.assertIn("observe_docling_container_health_without_redeploy", text)
        self.assertNotIn("docker logs", text)
        self.assertNotIn("print(result.stdout)", text)


if __name__ == "__main__":
    unittest.main()
