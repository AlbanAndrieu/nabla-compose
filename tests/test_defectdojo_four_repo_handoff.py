"""Offline four-repository DefectDojo collector, GitHub App and Cron contracts."""

from __future__ import annotations

from hashlib import sha256
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
SECURITY = ROOT / "scripts/security"
sys.path.insert(0, str(SECURITY))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, SECURITY / file)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


producer = load("compose_trivy_export", "export-defectdojo-compose-trivy.py")
collector = load("compose_trivy_poll", "poll-defectdojo-gh-artifacts.py")
launcher = load("nabla_cron", "run-nabla-github-app-cron.py")
vault = load("nabla_app_vault", "sync-nabla-github-app-vaultwarden.py")


class AllRepositoriesContracts(unittest.TestCase):
    def test_all_four_repositories_are_mapped_to_single_collector(self):
        configured = {s["repository"] for s in collector.SOURCES.values()}
        self.assertEqual(configured, {
            "AlbanAndrieu/nabla-compose",
            "AlbanAndrieu/fastapi-sample",
            "AlbanAndrieu/nabla-site-alban",
            "AlbanAndrieu/nabla-site-bababou",
        })
        self.assertEqual(collector.SOURCES["compose"]["workflow_files"]["trivy"], "security-source-sca.yml")

    def test_scanner_sanitizes_secrets_and_metadata_from_all_rows(self):
        raw = {
            "ArtifactName": "/tmp/private/home",
            "Results": [{
                "Target": "apps/service/package-lock.json",
                "Class": "lang-pkgs",
                "Type": "npm",
                "Secrets": [{"value": "VERY_PRIVATE"}],
                "Vulnerabilities": [
                    {"VulnerabilityID": "CVE-2026-1111", "PkgName": "demo",
                     "InstalledVersion": "1.0.0", "Severity": "HIGH",
                     "Description": "VERY_PRIVATE"},
                    {"VulnerabilityID": "CVE-2026-2222", "PkgName": "demo",
                     "Severity": "MEDIUM"},
                ],
            }],
        }
        saved = producer.sanitize(raw)
        self.assertNotIn("VERY_PRIVATE", json.dumps(saved))
        self.assertEqual(saved["Results"][0]["Target"], "package-lock.json")
        self.assertEqual(len(saved["Results"][0]["Vulnerabilities"]), 1)

    def test_producer_manifest_proves_source_sha_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            location = Path(tmp)
            raw, report, manifest = (
                location / "raw.json", location / "report.json",
                location / "manifest.json",
            )
            raw.write_text(json.dumps({
                "Results": [{
                    "Target": "uv.lock",
                    "Class": "lang-pkgs",
                    "Type": "python-pkg",
                    "Vulnerabilities": [{
                        "VulnerabilityID": "GHSA-fixture", "PkgName": "demo",
                        "Severity": "CRITICAL",
                    }],
                }],
            }))
            sha = "f" * 40
            producer.produce(raw, report, manifest, sha)
            info = json.loads(manifest.read_text())
            self.assertEqual(info["revision"], sha)
            self.assertEqual(info["report_sha256"], sha256(report.read_bytes()).hexdigest())
            self.assertTrue(collector.validate_compose_handoff({"head_sha": sha}, manifest.read_bytes(), report.read_bytes()))
            tampered = json.loads(report.read_text())
            tampered["Results"][0]["Secrets"] = [{"value": "stolen"}]
            with self.assertRaises(SystemExit):
                collector.validate_compose_handoff({"head_sha": sha}, manifest.read_bytes(), json.dumps(tampered).encode())

    def test_compose_stage_rejects_wrong_zip_members(self):
        run = {
            "id": 13, "name": "Source SCA Critical Gate", "head_branch": "master",
            "conclusion": "success", "status": "completed", "event": "schedule",
            "head_sha": "c" * 40,
        }
        metadata = {
            "artifacts": [{
                "id": 19, "name": "defectdojo-compose-trivy-" + run["head_sha"],
                "expired": False, "size_in_bytes": 99,
            }],
        }
        memory = BytesIO()
        with ZipFile(memory, "w") as zipped:
            zipped.writestr("extra.txt", "private")
        with (
            mock.patch.object(collector, "metadata", side_effect=[run, metadata]),
            mock.patch.object(collector, "api", return_value=memory.getvalue()),
        ):
            with self.assertRaises(SystemExit):
                collector.stage_compose_handoff("read-token", 13)

    def test_vaultwarden_bootstrap_and_cron_check_are_offline(self):
        with mock.patch.object(sys, "argv", ["vault", "--check"]):
            self.assertEqual(vault.main(), 0)
        with mock.patch.object(sys, "argv", ["cron", "--check"]):
            self.assertEqual(launcher.main(), 0)

    def test_cron_env_refuses_unlisted_keys_and_exposure(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            env = directory / ".env.secrets"
            config = directory / "github-app.json"
            key = directory / "github-app-private-key.pem"
            config.write_text("{}")
            key.write_text("fixture-only")
            env.write_text(
                f"GITHUB_APP_CONFIG_FILE={config}\n"
                f"GITHUB_APP_PRIVATE_KEY_FILE={key}\n"
                "DEFECTDOJO_FASTAPI_PULL_APPROVED=YES\n"
                "GITHUB_APP_PRIVATE_KEY_B64=not-allowed\n"
            )
            with (
                mock.patch.object(launcher, "APP", directory),
                mock.patch.object(launcher, "ENV", env),
                mock.patch.object(launcher, "CONFIG", config),
                mock.patch.object(launcher, "PEM", key),
                mock.patch.object(launcher, "verify_private"),
                mock.patch.object(launcher.os, "geteuid", return_value=0),
            ):
                with self.assertRaises(ValueError):
                    launcher.references()


if __name__ == "__main__":
    unittest.main()
