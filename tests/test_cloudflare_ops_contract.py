"""Offline contracts for safely disabled Cloudflare ops DNS/Tunnel adoption."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
TF = ROOT / "terraform/cloudflare-ops"


class CloudflareOpsContract(unittest.TestCase):
    def test_all_mutation_flags_default_false(self):
        variables = (TF / "variables.tofu").read_text(encoding="utf-8")
        for name in (
            "manage_dedicated_tunnel", "tunnel_creation_approved",
            "enable_ops_ingress", "publish_ops_dns", "dedicated_tunnel_verified",
            "access_policy_verified", "fastapi_origin_jwt_verified",
            "public_site_redaction_verified",
        ):
            self.assertRegex(
                variables,
                rf'variable "{name}" \{{[^}}]*default\s*=\s*false',
            )

    def test_dns_requires_ingress_access_jwt_and_redaction(self):
        source = (TF / "main.tofu").read_text(encoding="utf-8")
        self.assertIn('name    = "ops"', source)
        self.assertIn('content = "${local.tunnel_id}.cfargotunnel.com"', source)
        self.assertIn("proxied = true", source)
        self.assertIn("var.access_policy_verified", source)
        self.assertIn("var.fastapi_origin_jwt_verified", source)
        self.assertIn("var.public_site_redaction_verified", source)
        self.assertIn("var.enable_ops_ingress", source)
        self.assertEqual(source.count("prevent_destroy = true"), 3)
        self.assertNotIn("no_tls_verify = true", source)

    def test_ingress_owns_one_hostname_and_catch_all(self):
        source = (TF / "main.tofu").read_text(encoding="utf-8")
        self.assertIn('ops_hostname = "ops.albandrieu.com"', source)
        self.assertIn('service = "http_status:404"', source)
        self.assertIn("aud_tag   = [var.access_application_audience]", source)
        self.assertIn("required  = true", source)
        self.assertIn("var.dedicated_tunnel_verified", source)
        self.assertNotIn("defectdojo.int.albandrieu.com", source)

    def test_terragrunt_is_disabled_and_private(self):
        source = (ROOT / "infrastructure/cloudflare-ops/terragrunt.hcl").read_text()
        for name in ("manage_dedicated_tunnel", "enable_ops_ingress", "publish_ops_dns"):
            self.assertRegex(source, rf"{name}\s*=\s*false")
        self.assertIn('include "root"', source)
        self.assertNotIn("CLOUDFLARE_API_TOKEN", source)
        self.assertFalse(re.search(r"(?i)(token|password|secret)\s*=\s*\".+\"", source))


if __name__ == "__main__":
    unittest.main()
