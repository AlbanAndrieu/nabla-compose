"""Offline Defender Free guardrails — no Azure account, billing or network calls."""
from pathlib import Path
import ast
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[1]
TF = ROOT / "terraform/defender-free"
AUDIT = ROOT / "scripts/azure/defender-free-audit.py"


class DefenderFreeContract(unittest.TestCase):
    def test_pricing_is_free_and_opt_in_is_disabled(self):
        config = (TF / "main.tofu").read_text()
        self.assertIn('tier          = "Free"', config)
        self.assertIn('resource_type = "CloudPosture"', config)
        self.assertIn('default     = false', config)
        self.assertIn('prevent_destroy = true', config)
        self.assertNotIn('tier          = "Standard"', config)
        self.assertNotIn('resource "azurerm_security_center_subscription_pricing" "servers"', config)
        self.assertNotIn("azurerm_security_center_auto_provisioning", config)
        self.assertIn('backend "remote" {}', config)

    def test_read_only_audit_script(self):
        source = AUDIT.read_text()
        ast.parse(source)
        self.assertIn('"--method", "get"', source)
        self.assertNotIn('"--method", "put"', source.lower())
        self.assertNotIn('"--method", "post"', source.lower())
        spec = importlib.util.spec_from_file_location("defender_free_audit", AUDIT)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        safe, plans = module.evaluate_pricing({"value": [
            {"name": "CloudPosture", "properties": {"pricingTier": "Free"}},
            {"name": "VirtualMachines", "properties": {"pricingTier": "Free"}},
        ]})
        self.assertTrue(safe)
        self.assertEqual(len(plans), 2)
        safe, _ = module.evaluate_pricing({"value": [
            {"name": "CloudPosture", "properties": {"pricingTier": "Standard"}}
        ]})
        self.assertFalse(safe)
        with self.assertRaises(ValueError):
            module.evaluate_pricing({"value": []})

    def test_state_separation_and_foundational_not_equivalent(self):
        guide = (TF / "README.md").read_text()
        self.assertIn("not proof that Foundational CSPM", guide)
        self.assertIn("Do NOT reuse Entra", guide)
        self.assertIn("NOT APPLIED", guide)
        self.assertIn("specific workspaces", guide)


if __name__ == "__main__":
    unittest.main()
