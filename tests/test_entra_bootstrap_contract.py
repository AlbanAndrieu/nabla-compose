"""Offline contract: Entra Nabla's two GitHub OIDC identities and CI gates."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
READ = lambda path: (ROOT / path).read_text(encoding="utf-8")


class EntraBootstrapContract(unittest.TestCase):
    def test_distinct_oidc_subjects_and_graph_roles(self):
        tf = READ("terraform/entra/bootstrap.tofu")
        self.assertIn('plan  = "Application.Read.All"', tf)
        self.assertIn('apply = "Application.ReadWrite.OwnedBy"', tf)
        for resource in ('"azuread_application" "ci_identity"',
                         '"azuread_service_principal" "ci_identity"',
                         '"azuread_application_federated_identity_credential" "ci_github"'):
            self.assertIn(resource, tf)
        self.assertIn('subject        = "repo:AlbanAndrieu/nabla-compose:environment:entra-nabla-', tf)
        self.assertIn('issuer         = "https://token.actions.githubusercontent.com"', tf)
        self.assertIn('audiences      = ["api://AzureADTokenExchange"]', tf)
        self.assertIn('sign_in_audience = "AzureADMyOrg"', tf)
        self.assertIn('use_existing                 = true', tf)
        self.assertEqual(tf.count("prevent_destroy = true"), 3)
        self.assertNotIn('resource "azuread_application_password"', tf)
        self.assertNotIn('resource "azuread_app_role_assignment"', tf)
        self.assertNotIn("azurerm_role_assignment", tf)

    def test_explicit_bootstrap_and_ci_scope(self):
        v = READ("terraform/entra/variables.tofu")
        main = READ("terraform/entra/main.tofu")
        ci = READ(".github/workflows/entra.yml")
        self.assertIn('variable "enable_ci_identity_bootstrap"', v)
        self.assertIn('variable "enable_workload_pilot"', v)
        self.assertIn('default     = false', v)
        self.assertIn('var.enable_workload_pilot ? toset(["reader", "denied"]) : toset([])', main)
        self.assertIn('TF_VAR_enable_ci_identity_bootstrap: "true"', ci)
        self.assertIn('TF_VAR_enable_workload_pilot: "false"', ci)
        self.assertIn('vars.ENTRA_NABLA_OPERATOR_OBJECT_ID', ci)
        self.assertIn('vars.ENTRA_NABLA_TENANT_ID', ci)
        self.assertIn('TF_VAR_ci_bootstrap_operator_object_id', ci)
        self.assertIn('backend "remote"', READ("terraform/entra/backend.tofu"))

    def test_no_automatic_graph_consent_or_paid_defender(self):
        tf = READ("terraform/entra/bootstrap.tofu")
        self.assertIn("REQUESTS an application permission", tf)
        self.assertNotIn('resource "azuread_app_role_assignment"', tf)
        self.assertNotIn('resource "azurerm_security_center_subscription_pricing"', tf)


if __name__ == "__main__":
    unittest.main()
