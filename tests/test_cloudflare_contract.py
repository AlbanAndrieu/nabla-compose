"""Offline contracts for the import-first Cloudflare OpenTofu unit."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
TF = ROOT / "terraform/cloudflare"
CAPTURE = ROOT / "scripts/cloudflare/capture-homelab-tofu.sh"


def module_source() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(TF.glob("*.tofu")))


class CloudflareContract(unittest.TestCase):
    def test_provider_is_pinned_and_token_stays_in_environment(self):
        source = module_source()
        self.assertRegex(source, r'version\s*=\s*"= 5\.\d+\.\d+"')
        self.assertIn('provider "cloudflare" {}', source)
        self.assertNotRegex(source, r"(?i)\b(api_token|api_key)\s*=")

    def test_every_resource_is_imported_first(self):
        imports = (TF / "imports.tofu").read_text(encoding="utf-8")
        expected = {
            "cloudflare_zero_trust_tunnel_cloudflared_config.homelab":
                '"${var.account_id}/${var.tunnel_id}"',
            "cloudflare_dns_record.fastapi_sample":
                '"${var.zone_id}/${var.fastapi_sample_dns_record_id}"',
            "cloudflare_zero_trust_access_application.fastapi_sample":
                '"accounts/${var.account_id}/${var.fastapi_sample_access_application_id}"',
            "cloudflare_zero_trust_access_application.fastapi_sample_api":
                '"accounts/${var.account_id}/${var.fastapi_sample_api_access_application_id}"',
        }
        for address, import_id in expected.items():
            self.assertRegex(
                imports,
                rf"to = {re.escape(address)}\n\s*id = {re.escape(import_id)}",
            )
        # Resources that never existed in the dashboard: created by the module, never imported.
        created = {
            f"cloudflare_zero_trust_access_application.{name}"
            for name in ("keycloak_oidc", "joplin", "vaultwarden_admin")
        }
        resources = re.findall(r'resource "(\w+)" "(\w+)"', module_source())
        for kind, name in resources:
            if f"{kind}.{name}" in created:
                self.assertNotIn(f"to = {kind}.{name}\n", imports)
                continue
            self.assertIn(f"to = {kind}.{name}\n", imports)

    def test_postgres_is_not_published(self):
        # Internal-only since 2026-11-10: no tunnel route, no Access app, CNAME retired.
        source = module_source()
        self.assertNotIn('hostname       = "postgres.albandrieu.com"', source)
        self.assertNotIn("tcp://172.17.0.24:5432", source)
        policy = (ROOT / "terraform/cloudflare/dns-policy.yaml").read_text()
        self.assertIn("- postgres.albandrieu.com\n", policy)

    def test_declared_resources_cannot_be_destroyed(self):
        source = module_source()
        self.assertEqual(
            len(re.findall(r'^resource "', source, re.MULTILINE)),
            source.count("prevent_destroy = true"),
        )

    def test_keycloak_bypass_never_covers_the_master_realm(self):
        source = (TF / "access.tofu").read_text(encoding="utf-8")
        block = source.split('"keycloak_oidc"', 1)[1].split("\nresource ", 1)[0]
        self.assertIn("access_policy_everyone_bypass_id", block)
        self.assertNotRegex(block, r'uri\s*=\s*"keycloak\.albandrieu\.com(/realms/master)?/?"')

    def test_terragrunt_inherits_private_garage_state(self):
        source = (ROOT / "infrastructure/cloudflare/terragrunt.hcl").read_text()
        self.assertIn('include "root"', source)
        self.assertIn('find_in_parent_folders("terraform/cloudflare")', source)
        self.assertFalse(re.search(r"(?i)(token|password|secret)\s*=", source))

    def test_capture_is_read_only_and_hides_the_token(self):
        script = CAPTURE.read_text(encoding="utf-8")
        self.assertNotRegex(script, r"(?i)-X\b|--request|\b(POST|PUT|PATCH|DELETE)\b")
        self.assertNotRegex(script, r"(?m)^\s*tofu\b.*\b(apply|import|state)\b")
        self.assertIn("-H @-", script)
        self.assertIn("-generate-config-out=generated.tofu", script)
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/terraform/cloudflare/generated.tofu", gitignore)


if __name__ == "__main__":
    unittest.main()
