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
  # the shared tunnel configuration, the DNS records of the 20 zones and the
  # MTA-STS Worker with its custom domains (mail.tofu).
  opentofu_account_permissions = ["Access: Apps and Policies Write", "Cloudflare Tunnel Write", "Workers Scripts Write"]
  opentofu_zone_permissions    = ["DNS Write", "Workers Routes Write"]
  # Managed Transforms of albandrieu.com only (managed-transforms.tofu). "Zone
  # Transform Rules Write" is listed by the API spec yet GET managed_headers
  # answers 403 with it (22/11/2026): the dedicated group is required.
  # Bot settings of albandrieu.com (bot-management.tofu, Bot Fight Mode off, 27/11/2026).
  opentofu_home_zone_permissions = ["Managed headers Write", "Bot Management Write"]
  opentofu_missing_permissions = concat(
    [for name in local.opentofu_account_permissions : name if !contains(keys(local.account_group_ids), name)],
    [for name in concat(local.opentofu_zone_permissions, local.opentofu_home_zone_permissions) : name if !contains(keys(local.zone_group_ids), name)],
  )
  # CrowdSec Cloudflare Worker bouncer (apps/crowdsec/cloudflare-worker-bouncer.yaml):
  # the permissions its documentation lists, on albandrieu.com only.
  bouncer_account_permissions = ["Turnstile Sites Write", "Workers KV Storage Write", "Workers Scripts Write", "Account Settings Read", "Account Analytics Read"]
  bouncer_zone_permissions    = ["DNS Read", "Workers Routes Write", "Zone Read"]
  bouncer_missing_permissions = concat(
    [for name in local.bouncer_account_permissions : name if !contains(keys(local.account_group_ids), name)],
    [for name in local.bouncer_zone_permissions : name if !contains(keys(local.zone_group_ids), name)],
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
      # The other zones only for the mail records of terraform/cloudflare/mail.tofu.
      resources = jsonencode({
        for id in concat([var.zone_id, var.albanandrieu_zone_id], values(var.mail_zone_ids)) :
        "com.cloudflare.api.account.zone.${id}" => "*"
      })
    },
    {
      effect            = "allow"
      permission_groups = [for name in local.opentofu_home_zone_permissions : { id = local.zone_group_ids[name][0] }]
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

# The bouncer runs on TrueNAS behind the same Freebox WAN address as the operator,
# so it reuses the operator client-IP list.
resource "cloudflare_account_token" "crowdsec_bouncer" {
  account_id = var.account_id
  name       = "nabla-crowdsec-cloudflare-bouncer"
  expires_on = var.opentofu_token_expires_on

  policies = [
    {
      effect            = "allow"
      permission_groups = [for name in local.bouncer_account_permissions : { id = local.account_group_ids[name][0] }]
      resources         = jsonencode({ "com.cloudflare.api.account.${var.account_id}" = "*" })
    },
    {
      effect            = "allow"
      permission_groups = [for name in local.bouncer_zone_permissions : { id = local.zone_group_ids[name][0] }]
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
      condition     = length(local.bouncer_missing_permissions) == 0
      error_message = "Unknown permission group names: ${join(", ", local.bouncer_missing_permissions)}"
    }
  }
}

# Pipe `tofu output -raw crowdsec_bouncer_token` into the bouncer runtime secret
# (CLOUDFLARE_CROWDSEC_BOUNCER_TOKEN) and Vaultwarden, never to a terminal.
output "crowdsec_bouncer_token" {
  description = "CLOUDFLARE_CROWDSEC_BOUNCER_TOKEN value (sensitive)."
  value       = cloudflare_account_token.crowdsec_bouncer.value
  sensitive   = true
}
