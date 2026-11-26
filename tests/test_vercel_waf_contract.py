"""Offline contract tests for Bababou Vercel WAF policy (no secrets/network)."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "terraform/vercel-waf/main.tf"
TERRAGRUNT = ROOT / "infrastructure/vercel-waf/terragrunt.hcl"
RUNBOOK = ROOT / "terraform/vercel-waf/README.md"


class BababouWafContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = CONFIG.read_text(encoding="utf-8")
        cls.terragrunt = TERRAGRUNT.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK.read_text(encoding="utf-8")

    def test_enterprise_owasp_is_explicit_opt_in(self):
        self.assertRegex(
            self.config,
            r'variable "enable_owasp_blocking"\s*\{[^}]*default\s*=\s*false',
        )
        self.assertIn('var.enable_owasp_blocking ? "deny" : "log"', self.config)
        for group in ("sqli", "xss", "rce"):
            with self.subTest(group=group):
                self.assertRegex(
                    self.config,
                    rf'\b{group}\s*=\s*\{{\s*action\s*=\s*local.owasp_attack_action,\s*active\s*=\s*true\s*\}}',
                )
        self.assertRegex(
            self.config,
            r'\bgen\s*=\s*\{\s*action\s*=\s*"log",\s*active\s*=\s*true\s*\}',
        )

    def test_firewall_bot_protection_and_destroy_guard(self):
        self.assertRegex(self.config, r'\benabled\s*=\s*true')
        self.assertRegex(
            self.config,
            r'bot_protection\s*\{\s*action\s*=\s*"challenge"\s*active\s*=\s*true',
        )
        self.assertRegex(self.config, r'prevent_destroy\s*=\s*true')

    def test_one_hobby_compatible_rate_rule(self):
        # Only one custom rule to respect Vercel Hobby's limit.
        self.assertEqual(len(re.findall(r'^\s*rule\s*\{', self.config, re.M)), 1)
        self.assertIn('action = "rate_limit"', self.config)
        self.assertIn('active      = true', self.config)
        self.assertRegex(self.config, r'\blimit\s*=\s*300\b')
        self.assertRegex(self.config, r'\bwindow\s*=\s*60\b')
        self.assertIn('keys   = ["ip"]', self.config)
        self.assertIn('algo   = "fixed_window"', self.config)
        self.assertNotRegex(self.config, r'(?m)^\s*action_duration\s*=')
        self.assertIn('action = "deny"', self.config)

    def test_only_verified_custom_domains_no_preview(self):
        actual_hosts = set(re.findall(r'value\s*=\s*"([^"]+)"', self.config))
        self.assertEqual(
            actual_hosts,
            {"www.bababou.com", "bababou.com", "bababou.albandrieu.com"},
        )
        self.assertNotIn("vercel.app", self.config)
        self.assertEqual(len(re.findall(r'type\s*=\s*"host"', self.config)), 3)
        self.assertEqual(len(re.findall(r'op\s*=\s*"eq"', self.config)), 3)

    def test_garage_ownership_and_safe_apply_runbook(self):
        self.assertIn('include "root"', self.terragrunt)
        self.assertIn('find_in_parent_folders("terraform/vercel-waf")', self.terragrunt)
        for required in ("terragrunt-safe.sh", "import", "NOT APPLIED", "rollback"):
            self.assertIn(required.lower(), self.runbook.lower())
        self.assertNotRegex(self.config, r'(?i)(api_token|access_key|secret_key)\s*=')


if __name__ == "__main__":
    unittest.main()
