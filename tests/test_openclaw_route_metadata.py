"""Standard-library contracts: provider audit never prints URLs or credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/openclaw-route-metadata.py"


class OpenClawRouteMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name) / "openclaw.json"

    def inspect(self, config):
        self.config.write_text(json.dumps(config), encoding="utf-8")
        env = dict(os.environ, OPENCLAW_CONFIG_PATH=str(self.config))
        return subprocess.run(
            [sys.executable, str(SCRIPT)], env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            timeout=10,
        )

    def test_redacts_endpoint_and_api_key(self):
        secret = "private-credential-test-marker"
        hostname = "private-host-test.invalid"
        result = self.inspect({
            "models": {"providers": {"litellm-main": {
                "baseUrl": "https://name:password@" + hostname + ":4000/v1",
                "apiKey": secret,
            }}},
            "agents": {"defaults": {"memorySearch": {"provider": "openai"}}},
        })
        self.assertEqual(result.returncode, 0)
        self.assertIn("provider=litellm-main", result.stdout)
        self.assertIn("credential_in_url=yes", result.stdout)
        self.assertIn("memory_provider=present", result.stdout)
        self.assertIn("route_owner=other_or_unverified", result.stdout)
        self.assertIn("key_representation=literal_or_unresolved", result.stdout)
        for private in (secret, hostname, "password"):
            self.assertNotIn(private, result.stdout + result.stderr)

    def test_truenas_and_local_provider_routes_are_classified(self):
        result = self.inspect({
            "models": {"providers": {
                "litellm-main": {
                    "baseUrl": "http://172.17.0.24:4000/v1",
                    "apiKey": {"source": "file", "provider": "openclaw-main", "id": "value"},
                },
                "litellm-cron": {
                    "baseUrl": "http://127.0.0.1:4000/v1",
                    "apiKey": "sk-SHOULD_NOT_PRINT",
                },
            }}
        })
        self.assertEqual(result.returncode, 0)
        self.assertIn("route_owner=truenas_litellm", result.stdout)
        self.assertIn("route_owner=workstation_litellm", result.stdout)
        self.assertIn("key_representation=secretref_object", result.stdout)
        self.assertNotIn("sk-SHOULD_NOT_PRINT", result.stdout)
        self.assertNotIn("openclaw-main", result.stdout)

    def test_workstation_lan_and_malformed_port_are_safe(self):
        result = self.inspect({
            "models": {"providers": {
                "litellm-main": {
                    "baseUrl": "http://172.17.0.57:4000/v1",
                    "apiKey": "sk-SHOULD_NOT_PRINT",
                },
                "litellm-cron": {
                    "baseUrl": "http://private-host.invalid:secret-port/v1",
                    "apiKey": "sk-SHOULD_NOT_PRINT",
                },
            }}
        })
        self.assertEqual(result.returncode, 0)
        self.assertIn("route_owner=workstation_lan_litellm", result.stdout)
        self.assertIn("route_owner=other_or_unverified", result.stdout)
        self.assertNotIn("private-host.invalid", result.stdout + result.stderr)
        self.assertNotIn("secret-port", result.stdout + result.stderr)
        self.assertNotIn("sk-SHOULD_NOT_PRINT", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
