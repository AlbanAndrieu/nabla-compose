"""Read-only DefectDojo REST attestation: synthetic payloads only."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SECURITY = Path(__file__).resolve().parents[1] / "scripts/security"
sys.path.insert(0, str(SECURITY))
spec = importlib.util.spec_from_file_location(
    "ctem_dojo_live_verify", SECURITY / "verify-defectdojo-test.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class LiveTestVerification(unittest.TestCase):
    def test_processed_is_scoped_to_same_test_and_engagement(self):
        obj = {"id": 321, "engagement": 42,
               "status": "Processed", "processing": False}
        self.assertEqual(mod.test_state(obj, 321, 42), "LIVE_TEST_PROCESSED")
        self.assertEqual(mod.test_state(obj, 321, 43), "INTEGRITY_MISMATCH")
        self.assertEqual(mod.test_state(obj, 11, 42), "INTEGRITY_MISMATCH")
        self.assertEqual(mod.test_state({**obj, "processing": True}, 321, 42),
                         "PENDING")
        self.assertEqual(mod.test_state({**obj, "status": "Failed"}, 321, 42),
                         "IMPORT_FAILED")
        self.assertEqual(mod.test_state({}, 321, 42), "UNVERIFIED")

    def test_findings_count_matches_exact_test_filter(self):
        good = {"count": 3, "results": [{"id": 1, "test": 321}],
                "next": "https://private/api/v2/findings/?page=2"}
        self.assertEqual(mod.indexed_count(good, 321), 3)
        self.assertIsNone(mod.indexed_count(good, 888))
        self.assertEqual(mod.indexed_count({"count": 0, "results": [],
                                            "next": None}, 321), 0)
        self.assertIsNone(mod.indexed_count({"count": 0, "results": [{"id": 1}],
                                             "next": None}, 321))
        self.assertIsNone(mod.indexed_count({"count": True, "results": []}, 321))

    def test_finished_test_requires_verifiable_findings_response(self):
        with mock.patch.object(mod, "validated_receipt", return_value=(321, 42)):
            calls = []
            def getter(path):
                calls.append(path)
                return ({"id": 321, "engagement": 42, "status": "Processed",
                         "processing": False} if "/tests/" in path
                        else {"count": 1, "results": [{"test": 321}], "next": None})
            report = mod.verify_live("compose", "trivy", 77, get=getter)
            self.assertEqual(report["state"], "LIVE_TEST_PROCESSED")
            self.assertEqual(report["indexed_findings"], 1)
            self.assertFalse(report["deduplication_verified"])
            self.assertEqual(calls, [
                "/api/v2/tests/321/", "/api/v2/findings/?test=321&limit=1"])

    def test_pending_test_does_not_read_findings(self):
        with mock.patch.object(mod, "validated_receipt", return_value=(321, 42)):
            paths = []
            def getter(path):
                paths.append(path)
                return {"id": 321, "engagement": 42,
                        "status": "Processing", "processing": True}
            state = mod.verify_live("compose", "trivy", 77, get=getter)
            self.assertEqual(state["state"], "PENDING")
            self.assertIsNone(state["indexed_findings"])
            self.assertEqual(len(paths), 1)

    def test_invalid_finding_filter_never_claims_indexing(self):
        with mock.patch.object(mod, "validated_receipt", return_value=(321, 42)):
            def getter(path):
                return ({"id": 321, "engagement": 42, "status": "Processed",
                         "processing": False} if "/tests/" in path
                        else {"count": 5, "results": [{"test": 999}],
                              "next": None})
            report = mod.verify_live("compose", "trivy", 77, get=getter)
            self.assertEqual(report["state"], "FINDINGS_UNVERIFIED")
            self.assertIsNone(report["indexed_findings"])

    def test_no_network_or_token_read_in_default_check(self):
        with (mock.patch.object(mod, "read_private_token",
                                side_effect=AssertionError("token accessed")),
              mock.patch.object(mod, "get_json",
                                side_effect=AssertionError("network accessed")),
              mock.patch.object(sys, "argv", ["verify", "--check"])):
            self.assertEqual(mod.main(), 0)

    def test_mismatched_import_source_does_not_select_another_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(mod.report_path("compose", "trivy", 77, root),
                             root / "nabla-compose/compose-77-trivy.json")
            with self.assertRaises(mod.VerificationError):
                mod.report_path("compose", "zap", 77, root)
            with self.assertRaises(mod.VerificationError):
                mod.report_path("bababou", "nuclei", 77, root)


if __name__ == "__main__":
    unittest.main()
