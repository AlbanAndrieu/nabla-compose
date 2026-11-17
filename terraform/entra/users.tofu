# Workstation-only test user: CI pins enable_user_management=false and
# check-plan.py rejects any azuread_user change.
data "azuread_domains" "initial" {
  count        = var.enable_user_management ? 1 : 0
  only_initial = true
}

resource "azuread_user" "test" {
  count                 = var.enable_user_management ? 1 : 0
  user_principal_name   = "${var.name_prefix}-user@${data.azuread_domains.initial[0].domains[0].domain_name}"
  display_name          = "${var.name_prefix} test user"
  password              = var.test_user_initial_password
  force_password_change = true
  depends_on            = [terraform_data.personal_tenant_guard]

  lifecycle {
    # One-time password: the user replaces it at first sign-in.
    ignore_changes = [password]
    precondition {
      condition     = var.test_user_initial_password != null
      error_message = "Export TF_VAR_test_user_initial_password from Vaultwarden first."
    }
  }
}
