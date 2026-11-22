# Offline contract (mocked provider, no Azure call):
# Mock uses the operator-reported initial domain for readability. This fixture
# neither proves directory ownership nor configures the live Azure provider.
#   tofu -chdir=terraform/entra init -backend=false
#   TF_VAR_test_user_initial_password=dummy tofu -chdir=terraform/entra test
mock_provider "azuread" {
  mock_data "azuread_client_config" {
    defaults = { tenant_id = "00000000-0000-0000-0000-000000000001" }
  }
  mock_data "azuread_domains" {
    defaults = { domains = [{
      domain_name   = "albanandrieuhotmail.onmicrosoft.com", initial = true, default = true, verified = true,
      admin_managed = true, root = true, authentication_type = "Managed", supported_services = []
    }] }
  }
  mock_resource "azuread_application_registration" {
    defaults = { client_id = "00000000-0000-0000-0000-000000000002" }
  }
}

variables {
  tenant_id              = "00000000-0000-0000-0000-000000000001"
  nabla_tenant_confirmed = true
}

run "bootstrap_explicit_opt_in_only" {
  command = plan

  assert {
    condition = (
      length(azuread_application.ci_identity) == 0 &&
      length(azuread_service_principal.ci_identity) == 0 &&
      length(azuread_application_federated_identity_credential.ci_github) == 0
    )
    error_message = "GitHub OIDC identity bootstrap must default to OFF."
  }
}

run "ci_default_creates_no_user" {
  command = plan

  assert {
    condition     = length(azuread_user.test) == 0 && output.test_user_principal_name == null
    error_message = "enable_user_management must default to false (CI scope)"
  }
}

run "user_requires_the_vaultwarden_password" {
  command = plan
  variables {
    enable_user_management     = true
    test_user_initial_password = null
  }
  expect_failures = [azuread_user.test]
}

run "user_gets_a_one_time_password_in_the_initial_domain" {
  command = plan
  variables {
    enable_user_management = true
  }

  assert {
    condition     = azuread_user.test[0].user_principal_name == "nabla-iam-user@albanandrieuhotmail.onmicrosoft.com"
    error_message = "the test user must live in the tenant's initial onmicrosoft.com domain"
  }
  assert {
    condition     = azuread_user.test[0].force_password_change
    error_message = "the initial password must be replaced at first sign-in"
  }
}
