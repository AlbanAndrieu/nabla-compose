"""Offline contracts for the import-first Cloudflare homelab OpenTofu unit."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
TF = ROOT / "terraform/cloudflare-homelab"
CAPTURE = ROOT / "scripts/cloudflare/capture-homelab-tofu.sh"


def module_source() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(TF.glob("*.tofu")))


class CloudflareHomelabContract(unittest.TestCase):
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
        resources = re.findall(r'resource "(\w+)" "(\w+)"', module_source())
        for kind, name in resources:
            self.assertIn(f"to = {kind}.{name}\n", imports)

    def test_declared_resources_cannot_be_destroyed(self):
        source = module_source()
        self.assertEqual(
            len(re.findall(r'^resource "', source, re.MULTILINE)),
            source.count("prevent_destroy = true"),
        )

    def test_terragrunt_inherits_private_garage_state(self):
        source = (ROOT / "infrastructure/cloudflare-homelab/terragrunt.hcl").read_text()
        self.assertIn('include "root"', source)
        self.assertIn('find_in_parent_folders("terraform/cloudflare-homelab")', source)
        self.assertFalse(re.search(r"(?i)(token|password|secret)\s*=", source))

    def test_capture_is_read_only_and_hides_the_token(self):
        script = CAPTURE.read_text(encoding="utf-8")
        self.assertNotRegex(script, r"(?i)-X\b|--request|\b(POST|PUT|PATCH|DELETE)\b")
        self.assertNotRegex(script, r"(?m)^\s*tofu\b.*\b(apply|import|state)\b")
        self.assertIn("-H @-", script)
        self.assertIn("-generate-config-out=generated.tofu", script)
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/terraform/cloudflare-homelab/generated.tofu", gitignore)


if __name__ == "__main__":
    unittest.main()
