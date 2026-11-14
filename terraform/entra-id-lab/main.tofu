# H16/P0: personal Entra Free tenant only, no app credentials or Azure RBAC.
data "azuread_client_config" "current" {}

resource "terraform_data" "personal_tenant_guard" {
  input = var.tenant_id
  lifecycle {
    precondition {
      condition     = var.lab_tenant_confirmed && data.azuread_client_config.current.tenant_id == var.tenant_id
      error_message = "Refusing changes until personal tenant is confirmed and the provider identity matches."
    }
  }
}

locals {
  groups    = toset(["readers", "operators"])
  workloads = toset(["reader", "denied"])
}

resource "azuread_group" "lab" {
  for_each                = local.groups
  display_name            = "${var.name_prefix}-${each.key}"
  description             = "Disposable Entra lab group"
  security_enabled        = true
  prevent_duplicate_names = true
  depends_on              = [terraform_data.personal_tenant_guard]
}

resource "azuread_application_registration" "workload" {
  for_each         = local.workloads
  display_name     = "${var.name_prefix}-workload-${each.key}"
  description      = "Entra Free homelab: no secrets or API permissions"
  sign_in_audience = "AzureADMyOrg"
  depends_on       = [terraform_data.personal_tenant_guard]
}

resource "azuread_service_principal" "workload" {
  for_each                     = local.workloads
  client_id                    = azuread_application_registration.workload[each.key].client_id
  account_enabled              = each.key != "denied"
  app_role_assignment_required = true
  depends_on                   = [terraform_data.personal_tenant_guard]
}

data "azuread_user" "existing" {
  for_each            = var.test_users
  user_principal_name = each.value.upn
  depends_on          = [terraform_data.personal_tenant_guard]
}

resource "azuread_group_member" "existing" {
  for_each         = var.test_users
  group_object_id  = azuread_group.lab[each.value.group].object_id
  member_object_id = data.azuread_user.existing[each.key].object_id
}
