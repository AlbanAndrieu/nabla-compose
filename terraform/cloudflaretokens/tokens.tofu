data "cloudflare_account_api_token_permission_groups_list" "all" {
  account_id = var.account_id
}

locals {
  # Some names (e.g. "Access: Apps and Policies Write") exist in both scopes.
  account_group_ids = {
    for group in data.cloudflare_account_api_token_permission_groups_list.all.result : group.name => group.id...
    if contains(group.scopes, "com.cloudflare.api.account")
  }
  zone_group_ids = {
    for group in data.cloudflare_account_api_token_permission_groups_list.all.result : group.name => group.id...
    if contains(group.scopes, "com.cloudflare.api.account.zone")
  }
  # Exactly what terraform/cloudflare plans and applies: Access applications,
  # the shared tunnel configuration and the albandrieu.com DNS records.
  opentofu_account_permissions = ["Access: Apps and Policies Write", "Cloudflare Tunnel Write"]
  opentofu_zone_permissions    = ["DNS Write"]
  opentofu_missing_permissions = concat(
    [for name in local.opentofu_account_permissions : name if !contains(keys(local.account_group_ids), name)],
    [for name in local.opentofu_zone_permissions : name if !contains(keys(local.zone_group_ids), name)],
  )
}

resource "cloudflare_account_token" "opentofu" {
  account_id = var.account_id
  name       = "nabla-opentofu"
  expires_on = var.opentofu_token_expires_on

  policies = [
    {
      effect            = "allow"
      permission_groups = [for name in local.opentofu_account_permissions : { id = local.account_group_ids[name][0] }]
      resources         = jsonencode({ "com.cloudflare.api.account.${var.account_id}" = "*" })
    },
    {
      effect            = "allow"
      permission_groups = [for name in local.opentofu_zone_permissions : { id = local.zone_group_ids[name][0] }]
      resources         = jsonencode({ "com.cloudflare.api.account.zone.${var.zone_id}" = "*" })
    },
  ]

  condition = {
    request_ip = {
      in = var.opentofu_token_client_ips
    }
  }

  lifecycle {
    precondition {
      condition     = length(local.opentofu_missing_permissions) == 0
      error_message = "Unknown permission group names: ${join(", ", local.opentofu_missing_permissions)}"
    }
  }
}

# Read with `tofu output -raw opentofu_token` piped straight into Vaultwarden;
# the value also lives in the Garage state, which must stay LAN-only.
output "opentofu_token" {
  description = "CLOUDFLARE_API_TOKEN_NABLA_OPENTOFU value (sensitive)."
  value       = cloudflare_account_token.opentofu.value
  sensitive   = true
}

output "opentofu_token_id" {
  description = "Token identifier, to inspect its policies in the dashboard."
  value       = cloudflare_account_token.opentofu.id
}
