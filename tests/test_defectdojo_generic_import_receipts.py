"""CTEM: at-most-once DefectDojo imports from approved GitHub Actions evidence.

No network, TrueNAS or API access is used by these tests.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SECURITY = Path(__file__).resolve().parents[1] / "scripts/security"
sys.path.insert(0, str(SECURITY))


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SECURITY / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


poll = load("generic_ctem_poller", "poll-defectdojo-gh-artifacts.py")
reconcile = load("generic_ctem_evidence", "reconcile-defectdojo-evidence.py")


class GenericImportReceiptsTest(unittest.TestCase):
    def make_report(self, folder: Path, run_id: int = 77) -> Path:
        folder.mkdir(parents=True, mode=0o700, exist_ok=True)
        folder.chmod(0o700)
        report = folder / f"compose-{run_id}-trivy.json"
        report.write_bytes(b'{"Results":[]}')
        report.chmod(0o600)
        return report

    def approved_env(self):
        return {
            "DEFECTDOJO_IMPORT_APPROVED": "YES",
            "DEFECTDOJO_COMPOSE_ENGAGEMENT_ID": "42",
        }

    def test_exactly_one_submission_and_reconciliation(self):
        with tempfile.TemporaryDirectory() as temp:
            report = self.make_report(Path(temp) / "imports/nabla-compose")
            calls = []

            def accepted(kind, run_id, source):
                calls.append((kind, run_id, source))
                response = report.with_suffix(".import-response.json")
                response.write_text(json.dumps({
                    "test_id": 321, "status": "Processing",
                    "background_import": True,
                }), encoding="utf-8")
                response.chmod(0o600)

            with (mock.patch.object(poll, "COMPOSE_INBOX", report.parent),
                  mock.patch.dict(poll.os.environ, self.approved_env(), clear=True),
                  mock.patch.object(poll, "import_report", side_effect=accepted)):
                self.assertEqual(poll.import_reviewed_once("trivy", 77, "compose"),
                                 "ACKNOWLEDGED")
                self.assertEqual(poll.import_reviewed_once("trivy", 77, "compose"),
                                 "ALREADY_ACKNOWLEDGED")
                self.assertEqual(calls, [("trivy", 77, "compose")])
            self.assertEqual(reconcile.staged_state(report, "compose", 77),
                             "API_ACKNOWLEDGED_UNVERIFIED")
            self.assertEqual(json.loads(report.with_suffix(
                ".import.json").read_text())["state"], "acknowledged")

    def test_timeout_keeps_pending_and_does_not_repost(self):
        with tempfile.TemporaryDirectory() as temp:
            report = self.make_report(Path(temp) / "imports/nabla-compose")
            with (mock.patch.object(poll, "COMPOSE_INBOX", report.parent),
                  mock.patch.dict(poll.os.environ, self.approved_env(), clear=True),
                  mock.patch.object(poll, "import_report", side_effect=SystemExit("timeout")) as submit):
                with self.assertRaises(SystemExit):
                    poll.import_reviewed_once("trivy", 77, "compose")
                self.assertEqual(poll.import_reviewed_once("trivy", 77, "compose"),
                                 "PENDING_REVIEW")
                submit.assert_called_once()
            self.assertEqual(reconcile.staged_state(report, "compose", 77),
                             "PENDING_REVIEW")

    def test_api_receipt_without_test_id_never_claims_ack(self):
        with tempfile.TemporaryDirectory() as temp:
            report = self.make_report(Path(temp) / "imports/nabla-compose")

            def bad_receipt(*args, **kwargs):
                response = report.with_suffix(".import-response.json")
                response.write_text('{"status":"Processing"}', encoding="utf-8")
                response.chmod(0o600)

            with (mock.patch.object(poll, "COMPOSE_INBOX", report.parent),
                  mock.patch.dict(poll.os.environ, self.approved_env(), clear=True),
                  mock.patch.object(poll, "import_report", side_effect=bad_receipt)):
                with self.assertRaises(SystemExit):
                    poll.import_reviewed_once("trivy", 77, "compose")
            self.assertEqual(reconcile.staged_state(report, "compose", 77),
                             "PENDING_REVIEW")

    def test_changed_evidence_or_engagement_cannot_be_resent(self):
        with tempfile.TemporaryDirectory() as temp:
            report = self.make_report(Path(temp) / "imports/nabla-compose")
            marker = report.with_suffix(".import.json")
            marker.write_text(json.dumps({
                "run_id": 77, "source": "compose", "kind": "trivy",
                "sha256": "a" * 64, "engagement": "42",
                "state": "acknowledged",
            }))
            marker.chmod(0o600)
            with (mock.patch.object(poll, "COMPOSE_INBOX", report.parent),
                  mock.patch.dict(poll.os.environ, self.approved_env(), clear=True),
                  mock.patch.object(poll, "import_report") as submit):
                with self.assertRaises(SystemExit):
                    poll.import_reviewed_once("trivy", 77, "compose")
                submit.assert_not_called()
            self.assertEqual(reconcile.staged_state(report, "compose", 77),
                             "INTEGRITY_MISMATCH")

    def test_rejects_untrusted_report_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            report = self.make_report(Path(temp) / "imports/nabla-compose")
            report.unlink()
            report.symlink_to(report.parent)
            with (mock.patch.object(poll, "COMPOSE_INBOX", report.parent),
                  mock.patch.dict(poll.os.environ, self.approved_env(), clear=True),
                  mock.patch.object(poll, "import_report") as submit):
                with self.assertRaises(SystemExit):
                    poll.import_reviewed_once("trivy", 77, "compose")
                submit.assert_not_called()

    def test_readonly_inventory_never_calls_api_or_outputs_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            _unused_report = self.make_report(Path(temp) / "imports/nabla-compose")
            data = reconcile.inventory(Path(temp), reconcile.datetime.now(
                reconcile.timezone.utc))
            matched = [x for x in data["records"] if x.get("run_id") == 77]
            self.assertEqual(matched[0]["import"], "STAGED_NO_IMPORT_PROOF")
            self.assertIsNone(data["finding_count"])
            self.assertFalse(data["defectdojo_live_verified"])
            self.assertNotIn("/mnt/cpool", json.dumps(data))

    def test_receipt_shell_policy_is_bounded_and_syntax_valid(self):
        script = SECURITY / "import-scan-defectdojo.sh"
        content = script.read_text(encoding="utf-8")
        self.assertIn("DEFECTDOJO_IMPORT_RECEIPT_FILE", content)
        self.assertIn("receipt filename must match its staged report", content)
        self.assertIn("DefectDojo receipt exceeds private size limit", content)
        self.assertIn("close_old_findings=false", content)
        syntax = subprocess.run(["bash", "-n", str(script)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_collector_can_import_existing_stage_once(self):
        source = (SECURITY / "poll-defectdojo-gh-artifacts.py").read_text(
            encoding="utf-8")
        self.assertIn('result in {"STAGED", "ALREADY_STAGED"}', source)
        self.assertIn("outcome = import_reviewed_once(kind, run_id, source)",
                      source)


if __name__ == "__main__":
    unittest.main()
