"""Offline acceptance tests for private evidence reconciliation."""
import importlib.util
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/security/reconcile-defectdojo-evidence.py"
spec = importlib.util.spec_from_file_location("ctem_private_evidence", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
NOW = datetime(2026, 11, 28, 12, tzinfo=timezone.utc)


def save(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    path.chmod(0o600)


class PrivateEvidenceTests(unittest.TestCase):
    def test_unknown_not_failure_or_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            report = mod.inventory(Path(temp), NOW)
        self.assertIsNone(report["finding_count"])
        self.assertFalse(report["defectdojo_live_verified"])
        self.assertTrue(all(x["state"] == "NOT_OBSERVED" for x in report["records"]))

    def test_fastapi_acknowledged_is_not_ingested(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "imports/fastapi-sample"
            folder.mkdir(parents=True, mode=0o700)
            target = folder / "fastapi-104-trivy.json"
            target.write_bytes(b'{"Results":[]}')
            target.chmod(0o600)
            save(target.with_suffix(".import.json"), {
                "run_id": 104, "sha256": sha256(target.read_bytes()).hexdigest(),
                "engagement": "42", "state": "acknowledged"})
            self.assertEqual(mod.staged_state(target, "fastapi-sample", 104),
                             "API_ACKNOWLEDGED_UNVERIFIED")
            target.write_bytes(b'{"Results":[{}]}')
            self.assertEqual(mod.staged_state(target, "fastapi-sample", 104),
                             "INTEGRITY_MISMATCH")

    def test_symlink_and_staged_file_never_confirm(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "imports/nabla-compose"
            folder.mkdir(parents=True, mode=0o700)
            p = folder / "compose-77-trivy.json"
            p.write_text("{}")
            p.chmod(0o600)
            self.assertEqual(mod.staged_state(p, "compose", 77),
                             "STAGED_NO_IMPORT_PROOF")
            p.unlink()
            p.symlink_to(folder)
            self.assertEqual(mod.staged_state(p, "compose", 77), "INVALID_EVIDENCE")

    def test_private_zap_requires_archived_xml_and_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "20261128T120000Z-aabbccdd"
            folder.mkdir(mode=0o700)
            xml = folder / "report-full.xml"
            xml.write_bytes(b"<OWASPZAPReport/>")
            xml.chmod(0o600)
            save(folder / "manifest.json", {
                "run_id": folder.name, "scan_state": "COMPLETE",
                "import_state": "CONFIRMED",
                "last_import_receipt": "defectdojo-response.json",
                "outputs": {"report-full.xml": {
                    "sha256": sha256(xml.read_bytes()).hexdigest()}}})
            self.assertEqual(mod.private_zap(folder), ("COMPLETE", "UNVERIFIED"))
            save(folder / "defectdojo-response.json", {
                "test_id": 7, "status": "Processed", "processing": False})
            self.assertEqual(mod.private_zap(folder),
                             ("COMPLETE", "ARCHIVED_PROCESSING_CONFIRMED"))
            xml.write_bytes(b"tampered")
            self.assertEqual(mod.private_zap(folder),
                             ("INTEGRITY_MISMATCH", "NOT_VERIFIED"))

    def test_archived_async_zap_status_is_bound_to_original_test(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "20261128T120000Z-0a0b0c0d"
            folder.mkdir(mode=0o700)
            xml = folder / "report-full.xml"
            xml.write_bytes(b"<OWASPZAPReport/>")
            xml.chmod(0o600)
            save(folder / "manifest.json", {
                "run_id": folder.name, "scan_state": "COMPLETE",
                "import_state": "CONFIRMED",
                "last_import_receipt": "defectdojo-response.json",
                "outputs": {"report-full.xml": {
                    "sha256": sha256(xml.read_bytes()).hexdigest()}},
            })
            save(folder / "defectdojo-response.json", {
                "test_id": 321, "status": "Processing",
                "background_import": True,
            })
            status = folder / "defectdojo-test-status-1234abcd-1.json"
            save(status, {"id": 321, "status": "Processed",
                          "processing": False})
            self.assertEqual(mod.private_zap(folder),
                             ("COMPLETE", "ARCHIVED_PROCESSING_CONFIRMED"))
            save(status, {"id": 322, "status": "Processed",
                          "processing": False})
            self.assertEqual(mod.private_zap(folder),
                             ("COMPLETE", "INTEGRITY_MISMATCH"))
            save(status, {"id": 321, "status": "Failed",
                          "processing": False})
            self.assertEqual(mod.private_zap(folder),
                             ("COMPLETE", "IMPORT_FAILED"))

    def test_report_contains_no_paths_or_findings(self):
        with tempfile.TemporaryDirectory() as temp:
            report = mod.inventory(Path(temp), NOW)
        encoded = json.dumps(report)
        self.assertNotIn("/mnt/cpool", encoded)
        self.assertNotIn("Authorization", encoded)
        self.assertNotIn("albanandrieu.com", encoded)


if __name__ == "__main__":
    unittest.main()
