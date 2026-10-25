"""Offline APISIX contracts; no real Docker requests or secrets."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1] / "apps" / "apisix"


class ApisixContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = yaml.safe_load((ROOT / "compose.yml").read_text())
        cls.config = yaml.safe_load((ROOT / "config/config.yaml").read_text())
        raw = (ROOT / "config/apisix.yaml").read_text()
        assert raw.rstrip().endswith("#END"), "APISIX hot-reload requires #END"
        cls.rules = yaml.safe_load(raw)

    def test_no_admin_or_etcd(self):
        self.assertEqual(self.config["deployment"]["role"], "data_plane")
        self.assertEqual(self.config["deployment"]["role_data_plane"]["config_provider"], "yaml")
        self.assertFalse(self.config["apisix"]["enable_admin"])
        self.assertNotIn("etcd", self.compose["services"])

    def test_isolated_opt_in_no_ingress(self):
        for service in self.compose["services"].values():
            self.assertEqual(service["profiles"], ["apisix"])
            self.assertEqual(service["restart"], "no")
            self.assertNotIn("ports", service)
            self.assertFalse(any(
                str(label).startswith("traefik.")
                for label in service.get("labels", {})
            ))
            self.assertEqual(service["networks"], ["isolated"])
        self.assertEqual(self.compose["name"], "apisix")
        apisix = self.compose["services"]["apisix"]
        self.assertEqual(apisix["x-nabla"]["id"], "apisix")
        self.assertEqual(apisix["x-nabla"]["status"], "planned")
        self.assertEqual(
            apisix["labels"]["com.albandrieu.nabla.entity-ref"],
            "component:default/apisix",
        )
        self.assertEqual(
            apisix["x-nabla"]["runtime"]["containerService"], "apisix"
        )
        self.assertTrue(self.compose["networks"]["isolated"]["internal"])

    def test_single_protected_mock_route(self):
        self.assertEqual(len(self.rules["routes"]), 1)
        route = self.rules["routes"][0]
        self.assertEqual(route["uri"], "/health")
        self.assertEqual(route["methods"], ["GET"])
        self.assertTrue(route["plugins"]["key-auth"]["hide_credentials"])
        self.assertEqual(route["plugins"]["limit-count"]["rejected_code"], 429)
        self.assertEqual(route["upstream"]["nodes"], {"echo:8080": 1})

    def test_secret_from_environment_and_no_real_origin(self):
        key = self.rules["consumers"][0]["plugins"]["key-auth"]["key"]
        self.assertEqual(key, "$env://APISIX_KEY")
        self.assertIn("APISIX_KEY", self.compose["services"]["apisix"]["environment"])
        raw = (ROOT / "config/apisix.yaml").read_text()
        self.assertNotIn("172.17.", raw)
        self.assertNotIn("fastapi-sample.fastapicloud.dev", raw)


class ApisixRollbackContract(unittest.TestCase):
    def test_down_requires_no_live_key_and_invokes_only_scoped_compose(self):
        script = ROOT.parents[1] / "scripts/truenas/apisix.sh"
        with tempfile.TemporaryDirectory() as workdir:
            root = Path(workdir)
            log = root / "docker-calls"
            envfile = root / "mock-docker-functions"
            envfile.write_text(
                'docker() { printf "%s\\n" "$*" >> "$MOCK_DOCKER_LOG"; }\n',
                encoding="utf-8",
            )
            env = os.environ.copy()
            env.pop("APISIX_KEY", None)
            env.update(BASH_ENV=str(envfile), MOCK_DOCKER_LOG=str(log))
            result = subprocess.run(
                ["bash", str(script), "down"], env=env,
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(log.read_text().splitlines()), 1)
            self.assertIn("--profile apisix down", log.read_text())
            self.assertNotIn("apisix-cleanup-placeholder", result.stdout + result.stderr)

    def test_up_and_smoke_reject_missing_key_before_docker(self):
        script = ROOT.parents[1] / "scripts/truenas/apisix.sh"
        env = os.environ.copy()
        env.pop("APISIX_KEY", None)
        for action in ("up", "smoke"):
            with self.subTest(action=action):
                result = subprocess.run(
                    ["bash", str(script), action],
                    env=env, capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("APISIX_KEY", result.stderr)

    def test_check_reports_container_metadata_without_key(self):
        script = ROOT.parents[1] / "scripts/truenas/apisix.sh"
        with tempfile.TemporaryDirectory() as workdir:
            root = Path(workdir)
            envfile = root / "mock-docker-functions"
            envfile.write_text(
                'docker() { '
                'if [[ "$1" == inspect ]]; then '
                'printf "running|none\\n"; '
                'elif [[ "$*" == *"ps -q"* ]]; then '
                'printf "abcdef123456\\n"; '
                'fi; }\n',
                encoding="utf-8",
            )
            env = os.environ.copy()
            env.pop("APISIX_KEY", None)
            env["BASH_ENV"] = str(envfile)
            result = subprocess.run(
                ["bash", str(script), "check"], env=env,
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("service=apisix runtime=running", result.stdout)
            self.assertIn("service=echo runtime=running", result.stdout)
            self.assertIn("health=none http=not_checked", result.stdout)
            self.assertNotIn("apisix-cleanup-placeholder", result.stdout)

    def test_check_absent_container_is_unverified_not_down(self):
        script = ROOT.parents[1] / "scripts/truenas/apisix.sh"
        with tempfile.TemporaryDirectory() as workdir:
            fake = Path(workdir) / "mock-docker-functions"
            fake.write_text('docker() { return 0; }\n', encoding="utf-8")
            env = os.environ.copy()
            env.pop("APISIX_KEY", None)
            env["BASH_ENV"] = str(fake)
            result = subprocess.run(
                ["bash", str(script), "check"], env=env,
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("runtime=not_deployed_or_ambiguous", result.stdout)
            self.assertNotIn("runtime=failed", result.stdout)

    def test_check_marks_unhealthy_container_failed(self):
        script = ROOT.parents[1] / "scripts/truenas/apisix.sh"
        with tempfile.TemporaryDirectory() as workdir:
            fake = Path(workdir) / "mock-docker-functions"
            fake.write_text(
                'docker() { '
                'if [[ "$1" == inspect ]]; then '
                'printf "running|unhealthy\\n"; '
                'elif [[ "$*" == *"ps -q"* ]]; then '
                'printf "abcdef123456\\n"; '
                'fi; }\n',
                encoding="utf-8",
            )
            env = os.environ.copy()
            env.pop("APISIX_KEY", None)
            env["BASH_ENV"] = str(fake)
            result = subprocess.run(
                ["bash", str(script), "check"], env=env,
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("runtime=failed http=not_checked", result.stdout)
            self.assertNotIn("apisix-cleanup-placeholder", result.stdout)

    def test_mixed_cli_modes_are_invalid(self):
        script = ROOT.parents[1] / "scripts/truenas/apisix.sh"
        result = subprocess.run(
            ["bash", str(script), "up", "down"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
