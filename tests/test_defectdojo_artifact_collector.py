"""Offline security regression for no-runner GitHub Actions artifact polling."""

from __future__ import annotations

import contextlib
import importlib.util
import json
from xml.etree import ElementTree
from io import BytesIO, StringIO
from pathlib import Path
import sys
from unittest import TestCase, main, mock
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
SECURITY = ROOT / "scripts/security"
sys.path.insert(0, str(SECURITY))
import github_actions_artifact_api as github  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


poll = load(SECURITY / "poll-defectdojo-gh-artifacts.py", "poll_artifacts")
pull = load(SECURITY / "pull-site-alban-security-report.py", "pull_site_reports")


class FakeOpener:
    def __init__(self, redirect):
        self.redirect = redirect
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        if len(self.requests) == 1:
            raise HTTPError(req.full_url, 302, "redirect", {"Location": self.redirect}, None)
        return BytesIO(b"fixture-zip-bytes")


class GitHubArtifactsTests(TestCase):
    def test_token_never_sent_to_external_artifact_host(self):
        opener = FakeOpener("https://safe.actions.githubusercontent.com/path?sig=fixture")
        with mock.patch.object(github.request, "build_opener", return_value=opener):
            data = github.api(
                "repos/AlbanAndrieu/nabla-site-alban/actions/artifacts/123/zip",
                "private-read-token",
            )
        self.assertEqual(data, b"fixture-zip-bytes")
        self.assertIn("Authorization", opener.requests[0].headers)
        self.assertNotIn("Authorization", opener.requests[1].headers)
        self.assertNotIn("private-read-token", str(opener.requests[1].headers))

    def test_reject_unsafe_redirects_and_routes(self):
        self.assertFalse(github.allowed_download_url("http://safe.actions.githubusercontent.com/x"))
        self.assertFalse(github.allowed_download_url("https://safe.actions.githubusercontent.com.evil.invalid/x"))
        self.assertFalse(github.allowed_download_url("https://127.0.0.1/secret"))
        self.assertFalse(github.allowed_download_url("https://example.invalid/secret"))
        self.assertTrue(github.allowed_download_url("https://safe.actions.githubusercontent.com/archive"))
        with self.assertRaises(github.GitHubArtifactError):
            github.api("repos/someone/other/actions/artifacts/1/zip", "secret")
        opener = FakeOpener("https://127.0.0.1/internal")
        with mock.patch.object(github.request, "build_opener", return_value=opener):
            with self.assertRaises(github.GitHubArtifactError):
                github.api(
                    "repos/AlbanAndrieu/nabla-site-alban/actions/artifacts/1/zip",
                    "secret",
                )
        self.assertEqual(len(opener.requests), 1)

    def test_reject_oversized_metadata(self):
        with self.assertRaises(github.GitHubArtifactError):
            github.bounded_read(BytesIO(b"x" * 9), 8)

    def test_only_successful_master_runs_selected(self):
        good = {
            "id": 123, "name": "Production DAST", "head_branch": "master",
            "conclusion": "success", "status": "completed", "event": "schedule", "head_sha": "a" * 40,
        }
        bad = dict(good, id=124, head_branch="malicious-branch")
        with mock.patch.object(poll, "metadata", return_value={"workflow_runs": [good, bad]}):
            found = poll.latest_runs("fixture")
        self.assertEqual(found, {"zap": 123})

    def test_recent_failure_or_pending_scan_blocks_older_success(self):
        good = {
            "id": 100, "name": "Production DAST", "head_branch": "master",
            "conclusion": "success", "status": "completed",
            "event": "schedule", "head_sha": "a" * 40,
        }
        for conclusion, status in (("failure", "completed"), (None, "in_progress")):
            bad = dict(good, id=101, conclusion=conclusion, status=status)
            with mock.patch.object(poll, "metadata", return_value={"workflow_runs": [good, bad]}):
                self.assertNotIn("zap", poll.latest_runs("fixture"))

    def test_filter_trivy_minimizes_to_high_critical_npm_lockfile(self):
        raw = {
            "Results": [
                {
                    "Target": "package-lock.json",
                    "Licenses": [{"secret": "PRIVATE_LICENSE"}],
                    "Misconfigurations": [{"secret": "PRIVATE_CONFIG"}],
                    "Vulnerabilities": [
                        {"VulnerabilityID": "CVE-2026-1234", "PkgName": "react",
                         "Severity": "HIGH", "InstalledVersion": "1.0",
                         "Secret": "PRIVATE_HTTP_HEADER"},
                        {"VulnerabilityID": "CVE-2026-5678", "PkgName": "react",
                         "Severity": "MEDIUM"},
                    ],
                },
            ],
        }
        sanitized = pull.filter_findings("trivy", json.dumps(raw).encode())
        self.assertNotIn(b"PRIVATE_", sanitized)
        result = json.loads(sanitized)
        self.assertEqual(len(result["Results"][0]["Vulnerabilities"]), 1)
        raw["Results"][0]["Vulnerabilities"][0]["Severity"] = "LOW"
        self.assertEqual(pull.filter_findings("trivy", json.dumps(raw).encode()), b"")

    def test_filter_nuclei_strips_raw_request_response_and_url_query(self):
        raw = {
            "template-id": "cve-2026-1234",
            "info": {"name": "Known public CVE", "severity": "high",
                     "description": "PRIVATE_DESCRIPTION"},
            "matched-at": "https://www.albanandrieu.com/login?token=PRIVATE_TOKEN",
            "request": "Authorization: Bearer PRIVATE_TOKEN",
            "response": "Set-Cookie: PRIVATE_COOKIE",
        }
        sanitized = pull.filter_findings("nuclei", (json.dumps(raw) + "\n").encode())
        self.assertNotIn(b"PRIVATE_", sanitized)
        saved = json.loads(sanitized)
        self.assertEqual(saved["matched-at"], "https://www.albanandrieu.com")
        self.assertEqual(saved["template-id"], "cve-2026-1234")

    def test_filter_zap_emits_minimal_xml_without_http_secrets(self):
        raw = {
            "site": [{
                "@name": "https://www.albanandrieu.com",
                "alerts": [{
                    "riskcode": "3", "pluginid": "10035", "alert": "Content policy",
                    "instances": [{"uri": "https://www.albanandrieu.com/auth?token=PRIVATE_TOKEN",
                                   "requestheader": "Authorization: PRIVATE_TOKEN"}],
                    "evidence": "PRIVATE_COOKIE",
                }],
            }],
        }
        sanitized = pull.filter_findings("zap", json.dumps(raw).encode())
        self.assertNotIn(b"PRIVATE_", sanitized)
        root = ElementTree.fromstring(sanitized)
        self.assertEqual(root.tag, "OWASPZAPReport")
        self.assertEqual(root.findtext("./site/alerts/alertitem/riskcode"), "3")
        self.assertEqual(
            root.findtext("./site/alerts/alertitem/instances/instance/uri"),
            "https://www.albanandrieu.com",
        )
        raw["site"][0]["alerts"][0]["riskcode"] = "1"
        self.assertEqual(pull.filter_findings("zap", json.dumps(raw).encode()), b"")

    def test_poll_default_is_offline_without_token_or_network(self):
        with (
            mock.patch.object(poll, "installation_token", side_effect=AssertionError("token touched")),
            mock.patch.object(poll, "metadata", side_effect=AssertionError("network called")),
            mock.patch.object(sys, "argv", ["poll", "--check"]),
            contextlib.redirect_stdout(StringIO()) as output,
        ):
            self.assertEqual(poll.main(), 0)
        self.assertIn("offline", output.getvalue())

    def test_automatic_import_needs_separate_opt_in(self):
        with (
            mock.patch.object(poll.os, "environ", {}),
            mock.patch.object(poll.os, "geteuid", return_value=0),
            mock.patch.object(poll.Path, "is_dir", return_value=True),
            mock.patch.object(sys, "argv", ["poll", "--pull-and-import"]),
        ):
            with self.assertRaises(SystemExit):
                poll.main()


if __name__ == "__main__":
    main()
