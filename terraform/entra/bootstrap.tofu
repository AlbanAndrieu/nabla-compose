# H16: bootstrap GitHub OIDC apps on the trusted workstation with a
# personal Entra FIDO2/YubiKey login. Resources share the existing Nabla HCP
# remote state. This is only configuration: no Azure call during static CI.
locals {
  ci_identities = {
    plan  = "Application.Read.All"
    apply = "Application.ReadWrite.OwnedBy"
  }
  enabled_ci_identities = var.enable_ci_identity_bootstrap ? local.ci_identities : {}
}

data "azuread_service_principal" "microsoft_graph" {
  count     = var.enable_ci_identity_bootstrap ? 1 : 0
  client_id = "00000003-0000-0000-c000-000000000000"
}

resource "azuread_application" "ci_identity" {
  for_each         = local.enabled_ci_identities
  display_name     = "entra-nabla-${each.key}"
  description      = "Nabla GitHub OIDC ${each.key}; no client secret"
  sign_in_audience = "AzureADMyOrg"
  owners           = [var.ci_bootstrap_operator_object_id]

  # Merely REQUESTS an application permission. Admin consent is not granted.
  required_resource_access {
    resource_app_id = "00000003-0000-0000-c000-000000000000"
    resource_access {
      id   = data.azuread_service_principal.microsoft_graph[0].app_role_ids[each.value]
      type = "Role"
    }
  }

  lifecycle {
    prevent_destroy = true
    precondition {
      condition = (
        var.nabla_tenant_confirmed &&
        data.azuread_client_config.current.tenant_id == var.tenant_id &&
        can(regex("^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$", var.ci_bootstrap_operator_object_id))
      )
      error_message = "Bootstrap requires verified personal Entra tenant and stable operator object ID."
    }
  }
}

# An app registration often already has a home-tenant enterprise application.
# use_existing reconciles it instead of creating a duplicate.
resource "azuread_service_principal" "ci_identity" {
  for_each                     = local.enabled_ci_identities
  client_id                    = azuread_application.ci_identity[each.key].client_id
  account_enabled              = true
  app_role_assignment_required = false
  owners                       = [var.ci_bootstrap_operator_object_id]
  use_existing                 = true

  lifecycle {
    prevent_destroy = true
  }
}

resource "azuread_application_federated_identity_credential" "ci_github" {
  for_each       = local.enabled_ci_identities
  application_id = azuread_application.ci_identity[each.key].id
  display_name   = "github-nabla-compose-${each.key}"
  description    = "Exact GitHub Actions environment; no client secret"
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:AlbanAndrieu/nabla-compose:environment:entra-nabla-${each.key}"
  audiences      = ["api://AzureADTokenExchange"]

  lifecycle {
    prevent_destroy = true
  }
}

output "entra_nabla_ci_client_ids" {
  description = "Populate ENTRA_GRAPH_CLIENT_ID in the matching GitHub environments."
  value       = { for name, app in azuread_application.ci_identity : name => app.client_id }
}

output "entra_nabla_ci_principal_object_ids" {
  description = "Verify enterprise principals before Graph admin consent."
  value       = { for name, sp in azuread_service_principal.ci_identity : name => sp.object_id }
}

output "entra_nabla_ci_federated_subjects" {
  value = {
    for name in keys(local.enabled_ci_identities) : name =>
    "repo:AlbanAndrieu/nabla-compose:environment:entra-nabla-${name}"
  }
}
