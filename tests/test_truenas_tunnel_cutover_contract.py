"""TrueNAS public admin must require Access and no longer depend on pfSense."""
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TrueNASTunnelCutoverContract(unittest.TestCase):
    def test_tunnel_uses_https_origin_with_verified_hostname(self) -> None:
        tunnel = (ROOT / "terraform/cloudflare/tunnel.tofu").read_text()
        self.assertIn('hostname = "truenas.albandrieu.com"', tunnel)
        self.assertIn('service = "https://172.17.0.24:7000"', tunnel)
        self.assertIn('origin_server_name = "truenas.albandrieu.com"', tunnel)
        self.assertIn("cloudflare_zero_trust_access_application.truenas_admin,", tunnel)

    def test_identity_gate_and_catalogue(self) -> None:
        access = (ROOT / "terraform/cloudflare/access.tofu").read_text()
        block = access.split('resource "cloudflare_zero_trust_access_application" "truenas_admin" {', 1)[1]
        self.assertIn("local.access_policy_nabla_id", block)
        self.assertNotIn("local.access_policy_everyone_bypass_id", block)
        overrides = json.loads((ROOT / "catalog/homelab-exposure-overrides.json").read_text())
        truenas = next(e for e in overrides["services"] if e["name"] == "TrueNAS")
        self.assertEqual(truenas["tunnelUrl"], "https://truenas.albandrieu.com")
        self.assertTrue(truenas["tunnelSecure"])
        self.assertTrue(truenas["cloudflareAccessRequired"])
        self.assertNotIn("securityException", truenas)

    def test_dns_two_step_migration_policy(self) -> None:
        policy = (ROOT / "terraform/cloudflare/dns-policy.yaml").read_text()
        retired = policy.split("retired_hostnames:", 1)[1].split("new_tunnel_hostnames:", 1)[0]
        new = policy.split("new_tunnel_hostnames:", 1)[1].split("unpublished_tunnel_hostnames:", 1)[0]
        self.assertNotIn("- truenas.albandrieu.com", retired)
        self.assertIn("- truenas.albandrieu.com", new)


if __name__ == "__main__":
    unittest.main()
