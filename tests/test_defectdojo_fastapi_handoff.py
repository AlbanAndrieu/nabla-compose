"""Shared TrueNAS collector: native Trivy artifact, no producer-side export."""

from __future__ import annotations

import contextlib
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
    "shared_dojo", SECURITY / "poll-defectdojo-gh-artifacts.py"
)
assert spec and spec.loader
poll = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poll)


def native_report(*, include_secret=False, findings=True):
    row = {
        "Target": "ghcr.io/albanandrieu/fastapi-sample:master",
        "Class": "os-pkgs", "Type": "debian",
        "Vulnerabilities": ([{"VulnerabilityID": "CVE-2026-12345",
                             "PkgName": "fixture", "Severity": "CRITICAL",
                             "Description": "native field retained"}]
                            if findings else []),
    }
    if include_secret:
        row["Secrets"] = [{"Match": "MUST_NOT_IMPORT"}]
    return json.dumps({"SchemaVersion": 2, "Results": [row]}).encode()


def archive(data, extra=False):
    sink = BytesIO()
    with ZipFile(sink, "w", compression=ZIP_DEFLATED) as z:
        z.writestr(poll.FASTAPI_REPORT, data)
        if extra:
            z.writestr("unapproved.json", b"{}")
    return sink.getvalue()


class FastapiSharedCollectorContract(unittest.TestCase):
    def test_existing_poller_lists_native_docker_scan(self):
        self.assertEqual(poll.SOURCES["fastapi-sample"]["repository"],
                         "AlbanAndrieu/fastapi-sample")
        self.assertEqual(poll.SOURCES["fastapi-sample"]["workflow_files"]["trivy"],
                         "docker-build.yml")
        self.assertEqual(poll.FASTAPI_REPORT, "trivy-results.json")
        with (mock.patch.object(poll, "installation_token",
                                side_effect=AssertionError("token read")),
              mock.patch.object(poll, "metadata",
                                side_effect=AssertionError("network read")),
              mock.patch.object(sys, "argv", ["poll", "--source", "fastapi-sample", "--check"]),
              contextlib.redirect_stdout(StringIO()) as output):
            self.assertEqual(poll.main(), 0)
        self.assertIn("fastapi-sample:trivy", output.getvalue())

    def test_native_trivy_not_transformed(self):
        raw = native_report()
        self.assertTrue(poll.validate_fastapi_handoff(raw))
        self.assertIn(b"native field retained", raw)
        self.assertFalse(poll.validate_fastapi_handoff(native_report(findings=False)))
        for bad in (native_report(include_secret=True), b"{}",
                    b'{"SchemaVersion":2,"Results":"unexpected"}',
                    b'{"SchemaVersion":2,"Results":[{"Misconfigurations":[{"ID":"x"}]}]}'):
            with self.subTest(bad=bad[:45]), self.assertRaises(SystemExit):
                poll.validate_fastapi_handoff(bad)

    def test_zip_members_and_run_provenance_required(self):
        run = {"id": 104, "head_sha": "a"*40, "head_branch": "master",
               "name": "Docker CI", "status": "completed",
               "conclusion": "success", "event": "schedule"}
        listing = {"artifacts": [{"id": 123,
                    "name": "defectdojo-fastapi-trivy-" + "a"*40,
                    "expired": False, "size_in_bytes": 4000}]}
        def metadata(route, token):
            return listing if route.endswith("/artifacts") else run
        with (mock.patch.object(poll, "metadata", side_effect=metadata),
              mock.patch.object(poll, "api", return_value=archive(native_report(), extra=True))):
            with self.assertRaises(SystemExit):
                poll.stage_fastapi_handoff("fixture-only", 104)
        with (mock.patch.object(poll, "metadata", side_effect=metadata),
              mock.patch.object(poll, "api", return_value=archive(native_report(findings=False)))):
            self.assertEqual(poll.stage_fastapi_handoff("fixture-only", 104),
                             "NO_ACTIONABLE_FINDINGS")
        run["head_branch"] = "untrusted"
        with mock.patch.object(poll, "metadata", side_effect=metadata):
            with self.assertRaises(SystemExit):
                poll.stage_fastapi_handoff("fixture-only", 104)

    def test_new_failure_blocks_previous_success(self):
        good = {"id": 111, "head_sha": "a"*40, "head_branch": "master",
                "name": "Docker CI", "status": "completed",
                "conclusion": "success", "event": "schedule"}
        bad = dict(good, id=112, conclusion="failure")
        with mock.patch.object(poll, "metadata",
                               return_value={"workflow_runs": [good, bad]}):
            self.assertEqual(poll.latest_runs("fixture", source="fastapi-sample"), {})


if __name__ == "__main__":
    unittest.main()
