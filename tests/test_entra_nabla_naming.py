"""Offline guard for Entra Nabla naming, tenant verification and CI OIDC boundaries."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
READ = lambda path: (ROOT / path).read_text(encoding="utf-8")


class EntraNablaNamingContract(unittest.TestCase):
    def test_oidc_environment_identity_exact_match(self):
        workflow = READ(".github/workflows/entra.yml")
        self.assertIn("'entra-nabla-plan'", workflow)
        self.assertIn("'entra-nabla-apply'", workflow)
        self.assertIn("vars.ENTRA_NABLA_TENANT_ID", workflow)
        self.assertIn("vars.ENTRA_NABLA_APPLY_ENABLED", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertNotIn("entra-lab-", workflow)
        self.assertNotIn("ENTRA_LAB_", workflow)
        self.assertNotIn("ARM_CLIENT_SECRET: ", workflow)

    def test_nabla_tenant_guard_and_private_backend(self):
        main = READ("terraform/entra/main.tofu")
        variables = READ("terraform/entra/variables.tofu")
        preflight = READ("scripts/entra/entra-nabla-preflight.sh")
        self.assertIn("var.nabla_tenant_confirmed", main)
        self.assertIn("data.azuread_client_config.current.tenant_id == var.tenant_id", main)
        self.assertIn('default = "nabla-iam"', variables)
        self.assertIn("ENTRA_NABLA_CONFIRMED", preflight)
        self.assertIn("ENTRA_NABLA_TENANT_ID", preflight)
        self.assertIn("az account show", preflight)
        self.assertIn('backend "remote"', READ("terraform/entra/backend.tofu"))
        self.assertFalse((ROOT / "scripts/entra/entra-lab-preflight.sh").exists())

    def test_readme_keeps_operator_authentication_hardware_first(self):
        doc = READ("docs/runbooks/entra-tenant-and-test-user.md")
        self.assertIn("YubiKey", doc)
        self.assertIn("entra-nabla-plan", doc)
        self.assertIn("entra-nabla-apply", doc)
        self.assertIn("entra-nabla-state", doc)
        self.assertIn("OIDC", doc)
        self.assertIn("NOT_APPLIED", doc)
        self.assertNotIn("ENTRA_LAB_TENANT_ID", doc)


if __name__ == "__main__":
    unittest.main()
