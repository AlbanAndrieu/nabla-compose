"""Offline contracts for the shared GitHub Actions DefectDojo collector.

The same TrueNAS poller handles site and fastapi sources. No network,
Github App, DefectDojo token or Cron configuration is required.
"""

from __future__ import annotations

import contextlib
from hashlib import sha256
from io import BytesIO, StringIO
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SECURITY = ROOT / "scripts/security"
sys.path.insert(0, str(SECURITY))
spec = importlib.util.spec_from_file_location(
    "shared_defectdojo_poller", SECURITY / "poll-defectdojo-gh-artifacts.py"
)
assert spec and spec.loader
poller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poller)


class SharedCollectorTests(unittest.TestCase):
    @staticmethod
    def fixture(severity="HIGH", extra=None):
        report = {"SchemaVersion": 2, "Results": [
            {"Target": "uv.lock", "Class": "lang-pkgs", "Type": "python-pkg",
             "Vulnerabilities": [
                 {"VulnerabilityID": "CVE-2026-12345",
                  "PkgName": "httpx", "InstalledVersion": "1.2.3",
                  "Severity": severity, **(extra or {})}]}]}
        raw = json.dumps(report).encode()
        revision = "a" * 40
        manifest = {
            "schema_version": 1, "project": "fastapi-sample",
            "scope": "uv.lock-only-high-critical",
            "mode": "master", "state": "complete", "scanner": "Trivy Scan",
            "policy_status": "needs_review" if severity == "CRITICAL" else "pass",
            "revision": revision, "source_report_sha256": "b" * 64,
            "report_file": poller.FASTAPI_REPORT, "artifact_sha256": sha256(raw).hexdigest(),
            "counts": {"HIGH": int(severity == "HIGH"), "CRITICAL": int(severity == "CRITICAL")},
        }
        run = {"id": 104, "head_sha": revision, "head_branch": "master",
               "name": "DefectDojo Trivy Handoff (FastAPI)", "status": "completed",
               "conclusion": "success", "event": "workflow_dispatch"}
        return run, json.dumps(manifest).encode(), raw

    @staticmethod
    def zip_contents(manifest: bytes, report: bytes, extra=False) -> bytes:
        buffer = BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr(poller.FASTAPI_REPORT, report)
            archive.writestr(poller.FASTAPI_MANIFEST, manifest)
            if extra:
                archive.writestr("secrets.txt", "NEVER")
        return buffer.getvalue()

    def test_shared_collector_has_one_explicit_fastapi_source(self):
        self.assertEqual(poller.SOURCES["fastapi-sample"]["repository"],
                         "AlbanAndrieu/fastapi-sample")
        self.assertEqual(poller.SOURCES["fastapi-sample"]["workflow_files"]["trivy"],
                         "defectdojo-trivy-handoff.yml")
        self.assertNotIn("fastapi-sample", poller.WORKFLOW_FILES)
        with (mock.patch.object(poller, "installation_token",
                                side_effect=AssertionError("token accessed")),
              mock.patch.object(poller, "metadata",
                                side_effect=AssertionError("network accessed")),
              mock.patch.object(sys, "argv", ["poll", "--source", "fastapi-sample", "--check"]),
              contextlib.redirect_stdout(StringIO()) as stdout):
            self.assertEqual(poller.main(), 0)
        self.assertIn("fastapi-sample:trivy", stdout.getvalue())

    def test_accepts_only_exact_trivy_allowlist_and_receipt(self):
        run, manifest, raw = self.fixture()
        self.assertTrue(poller.validate_fastapi_handoff(run, manifest, raw))
        run, manifest, raw = self.fixture("CRITICAL")
        self.assertTrue(poller.validate_fastapi_handoff(run, manifest, raw))
        report = json.loads(raw)
        report["Results"][0]["Vulnerabilities"][0]["Description"] = "PRIVATE TOKEN"
        with self.assertRaises(SystemExit):
            poller.validate_fastapi_handoff(run, manifest, json.dumps(report).encode())

    def test_rejects_bad_provenance_and_critical_masked_as_pass(self):
        run, manifest, raw = self.fixture("CRITICAL")
        for changed in ({"revision": "b" * 40}, {"policy_status": "pass"},
                        {"report_file": "private.json"}, {"scope": "full-filesystem"}):
            info = json.loads(manifest)
            info.update(changed)
            with self.subTest(changed=changed), self.assertRaises(SystemExit):
                poller.validate_fastapi_handoff(run, json.dumps(info).encode(), raw)

    def test_stage_verifies_exact_zip_and_uses_no_import(self):
        run, manifest, raw = self.fixture()
        listing = {"artifacts": [{
            "id": 123, "name": "defectdojo-fastapi-trivy-" + run["head_sha"],
            "expired": False, "size_in_bytes": 2000,
        }]}
        def metadata(route, token):
            if route.endswith("/artifacts"):
                return listing
            return run
        with (mock.patch.object(poller, "metadata", side_effect=metadata),
              mock.patch.object(poller, "api", return_value=self.zip_contents(manifest, raw, extra=True))):
            with self.assertRaises(SystemExit):
                poller.stage_fastapi_handoff("fixture-token", run["id"])
        with (mock.patch.object(poller, "metadata", side_effect=metadata),
              mock.patch.object(poller, "api", return_value=self.zip_contents(manifest, raw)),
              mock.patch.object(poller, "FASTAPI_INBOX", Path("/tmp/defectdojo-fixture-inexistent")),
              mock.patch.object(poller, "validate_fastapi_handoff", return_value=False)):
            self.assertEqual(poller.stage_fastapi_handoff("fixture-token", run["id"]),
                             "NO_ACTIONABLE_FINDINGS")

    def test_latest_failed_scan_blocks_older_success(self):
        good = {"id": 100, "name": "DefectDojo Trivy Handoff (FastAPI)",
                "head_branch": "master", "status": "completed", "conclusion": "success",
                "event": "workflow_dispatch", "head_sha": "a" * 40}
        bad = dict(good, id=101, conclusion="failure")
        with mock.patch.object(poller, "metadata",
                               return_value={"workflow_runs": [good, bad]}):
            self.assertEqual(poller.latest_runs("fixture", "fastapi-sample"), {})


if __name__ == "__main__":
    unittest.main()
