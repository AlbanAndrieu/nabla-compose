"""Contracts for the repository-owned OWASP DSOMM deployment."""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "apps" / "dsomm" / "compose.yml"
META = ROOT / "apps" / "dsomm" / "config" / "meta.yaml"
DOCKERFILE = ROOT / "apps" / "dsomm" / "baseline" / "Dockerfile"
RUNNER = ROOT / "apps" / "dsomm" / "baseline" / "run-baseline.sh"
README = ROOT / "apps" / "dsomm" / "README.md"
DEPLOY = ROOT / "scripts" / "truenas" / "deploy-dsomm.sh"


class DsommContractTests(unittest.TestCase):
    def test_ui_service_is_internal_repository_owned_dsomm(self) -> None:
        payload = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        service = payload["services"]["dsomm"]
        self.assertIn("wurstbrot/dsomm:latest", service["image"])
        port = service["ports"][0]
        self.assertEqual(8080, port["target"])
        self.assertEqual("31088", port["published"])
        self.assertEqual("172.17.0.24", port["host_ip"])
        self.assertEqual("dsomm", service["x-nabla"]["id"])
        self.assertEqual("planned", service["x-nabla"]["status"])
        self.assertEqual("truenas-app", service["x-nabla"]["runtime"]["provider"])
        self.assertEqual(31088, service["x-nabla"]["monitoring"]["port"])
        self.assertTrue(
            any("/srv/assets/YAML/meta.yaml:ro" in volume for volume in service["volumes"])
        )
        self.assertTrue(any("team-progress.yaml:/srv/assets/YAML/team-progress.yaml:ro" in volume for volume in service["volumes"]))
        self.assertTrue(any("team-evidence.yaml:/srv/assets/YAML/team-evidence.yaml:ro" in volume for volume in service["volumes"]))

    def test_baseline_is_manual_pinned_and_secret_backed(self) -> None:
        payload = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        service = payload["services"]["dsomm-baseline"]
        self.assertEqual(["manual"], service["profiles"])
        self.assertEqual("planned", service["x-nabla"]["status"])
        self.assertEqual("no", service["restart"])
        env_file = service["env_file"][0]
        self.assertEqual("/mnt/cpool/secrets/runtime/dsomm/.env.secrets", env_file["path"])
        self.assertFalse(env_file["required"])
        self.assertNotIn("GH_TOKEN", service.get("environment", {}))
        self.assertIn("/mnt/cpool/dsomm/reports:/reports", service["volumes"])
        self.assertEqual("automates", service["x-nabla"]["relations"][0]["type"])
        self.assertIn("3255561bc9162e335d2c79b72e12b1478075e610", COMPOSE.read_text(encoding="utf-8"))

    def test_baseline_image_and_runner_fail_closed(self) -> None:
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        runner = RUNNER.read_text(encoding="utf-8")
        self.assertIn("python:3.13-slim", dockerfile)
        self.assertIn("apt-get install -y --no-install-recommends ca-certificates git gh", dockerfile)
        self.assertIn("git -C /opt/dsomm-baseline fetch --depth 1 origin", dockerfile)
        self.assertIn('[[ -n "${GH_TOKEN:-}" ]]', runner)
        self.assertIn("/reports/*", runner)
        self.assertIn("gh auth status --hostname github.com", runner)
        self.assertIn("ALL", runner)
        self.assertIn("summarize-dsomm-baseline.py", dockerfile)
        self.assertIn("summarize-dsomm-baseline.py", runner)
        self.assertIn('chmod 0600 "${output}"', runner)
        self.assertIn("DSOMM_BASELINE_SUMMARY_OUTPUT", runner)

    def test_default_meta_uses_nabla_contexts_without_evidence_in_git(self) -> None:
        payload = yaml.safe_load(META.read_text(encoding="utf-8"))
        self.assertEqual(
            ["Nabla Homelab Platform", "FastAPI Sample", "Nabla Site Alban", "Nabla Site Bababou"],
            payload["teams"],
        )
        self.assertEqual(["default/model.yaml"], payload["activityFiles"])
        self.assertNotIn("evidence", payload)
        self.assertEqual("team-evidence.yaml", payload["teamEvidenceFile"])

    def test_deployer_uses_supported_truenas_custom_app_path(self) -> None:
        text = DEPLOY.read_text(encoding="utf-8")
        self.assertFalse(text.startswith("#!"))
        self.assertIn('MODE="${1:---check}"', text)
        self.assertIn("bootstrap-repository-storage.sh", text)
        self.assertIn("team-progress.yaml", text)
        self.assertIn("team-evidence.yaml", text)
        self.assertIn("chmod 0600", text)
        self.assertIn("truenas_reconcile_custom_app", text)
        self.assertIn("truenas_wait_app_running", text)
        self.assertIn("generate-service-topology.py --check", text)
        self.assertIn("generate-service-consumers.py --check", text)
        self.assertIn("x-nabla.status remains planned", text)

    def test_readme_keeps_baseline_as_supporting_evidence(self) -> None:
        text = README.read_text(encoding="utf-8")
        self.assertIn("evidence", text.lower())
        self.assertIn("not a maturity verdict", text)
        self.assertIn("least privilege", text)
        self.assertIn("Not Supported - Manual Process", text)


if __name__ == "__main__":
    unittest.main()
