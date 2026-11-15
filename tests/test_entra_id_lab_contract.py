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

    def test_test_user_is_workstation_only_with_one_time_password(self):
        users = (LAB / "users.tofu").read_text()
        self.assertRegex(users, r"count\s+= var\.enable_user_management \? 1 : 0")
        self.assertRegex(users, r"password\s+= var\.test_user_initial_password")
        self.assertRegex(users, r"force_password_change\s+= true")
        self.assertIn("ignore_changes = [password]", users)
        self.assertNotIn("random_password", users)
        variables = (LAB / "variables.tofu").read_text()
        self.assertRegex(variables, r'variable "enable_user_management" \{[^}]*default\s+= false')
        self.assertRegex(variables, r'variable "test_user_initial_password" \{[^}]*sensitive\s+= true')
        self.assertNotIn("test_user_initial_password", (LAB / "outputs.tofu").read_text())
        workflow = (ROOT / ".github/workflows/entra-id-lab.yml").read_text()
        self.assertIn('TF_VAR_enable_user_management: "false"', workflow)

    def test_refuses_remote_mode_without_running_azure(self):
        env = {"AGENT_EXECUTION_MODE": "offline"}
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/entra/entra-lab-preflight.sh")],
            cwd=ROOT, env=env, capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("ENTRA_LAB_BLOCKED", result.stderr)

    def test_private_backend_and_read_only_preflight(self):
        backend = (LAB / "backend.tofu").read_text()
        self.assertIn('backend "azurerm"', backend)
        self.assertIn("use_azuread_auth = true", backend)
        self.assertFalse((ROOT / "infrastructure/entra-id-lab/terragrunt.hcl").exists())
        preflight = (ROOT / "scripts/entra/entra-lab-preflight.sh").read_text()
        self.assertIn("AGENT_EXECUTION_MODE", preflight)
        self.assertIn("az account show", preflight)
        self.assertNotIn("az role assignment create", preflight)


if __name__ == "__main__":
    unittest.main()
