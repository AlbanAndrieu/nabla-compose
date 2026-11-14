"""Offline contract checks for the P0 Entra Free identity lab."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "terraform" / "entra-id-lab"


class EntraLabContract(unittest.TestCase):
    def test_safe_resources(self):
        main = (LAB / "main.tofu").read_text()
        self.assertIn("lab_tenant_confirmed &&", main)
        self.assertIn('resource "azuread_service_principal"', main)
        self.assertIn('account_enabled              = each.key != "denied"', main)
        for forbidden in ("azuread_application_password", 'resource "azuread_user"',
                          "azurerm_role_assignment", "required_resource_access"):
            self.assertNotIn(forbidden, main)

    def test_refuses_remote_mode_without_running_azure(self):
        env = {"AGENT_EXECUTION_MODE": "offline"}
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/entra/entra-lab-preflight.sh")],
            cwd=ROOT, env=env, capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("ENTRA_LAB_BLOCKED", result.stderr)

    def test_private_backend_and_read_only_preflight(self):
        config = (ROOT / "infrastructure/entra-id-lab/terragrunt.hcl").read_text()
        self.assertIn('include "root"', config)
        self.assertIn("ENTRA_LAB_TENANT_ID", config)
        preflight = (ROOT / "scripts/entra/entra-lab-preflight.sh").read_text()
        self.assertIn("AGENT_EXECUTION_MODE", preflight)
        self.assertIn("az account show", preflight)
        self.assertNotIn("az role assignment create", preflight)


if __name__ == "__main__":
    unittest.main()
