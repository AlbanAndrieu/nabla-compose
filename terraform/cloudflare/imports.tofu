# Import-first: every resource of this unit already exists in the Cloudflare
# dashboard. The first plan must show "will be imported", never "will be created".

import {
  to = cloudflare_zero_trust_tunnel_cloudflared_config.homelab
  id = "${var.account_id}/${var.tunnel_id}"
}

import {
  to = cloudflare_dns_record.fastapi_sample
  id = "${var.zone_id}/${var.fastapi_sample_dns_record_id}"
}

import {
  to = cloudflare_zero_trust_access_application.fastapi_sample
  id = "accounts/${var.account_id}/${var.fastapi_sample_access_application_id}"
}

import {
  to = cloudflare_zero_trust_access_application.fastapi_sample_api
  id = "accounts/${var.account_id}/${var.fastapi_sample_api_access_application_id}"
}

# Tunnel CNAMEs already exist: adopt them before any change.
import {
  for_each = {
    for hostname, id in var.dns_tunnel_record_ids : hostname => id
    if contains(local.tunnel_hostnames, hostname)
  }
  to = module.dns_records.cloudflare_dns_record.tunnel[each.key]
  id = "${var.zone_id}/${each.value}"
}

import {
  to = cloudflare_zero_trust_tunnel_cloudflared_config.workstation
  id = "${var.account_id}/${var.workstation_tunnel_id}"
}

import {
  for_each = {
    for hostname, id in var.dns_tunnel_record_ids : hostname => id
    if contains(local.workstation_tunnel_hostnames, hostname)
  }
  to = module.workstation_dns_records.cloudflare_dns_record.tunnel[each.key]
  id = "${var.zone_id}/${each.value}"
}

# Retired records are imported only during the adopt phase.
import {
  for_each = {
    for key, id in var.dns_retired_record_ids : key => id
    if var.dns_retirement_phase == "adopt" && contains(local.dns_policy.retired_hostnames, split("/", key)[0])
  }
  to = module.dns_records.cloudflare_dns_record.retired[each.key]
  id = "${var.zone_id}/${each.value}"
}

# Apex SPF records of mail.tofu exist in both zones: adopt them before -all.
import {
  for_each = var.mail_spf_record_ids
  to       = cloudflare_dns_record.mail_spf[each.key]
  id       = "${local.mail_zone_ids[each.key]}/${each.value}"
}

# Existing DMARC records of mail.tofu: adopt them before rua/ruf move.
import {
  for_each = var.mail_dkim_record_ids
  to       = cloudflare_dns_record.mail_dkim[each.key]
  id       = "${local.mail_zone_ids[each.key]}/${each.value}"
}

import {
  for_each = var.mail_dmarc_record_ids
  to       = cloudflare_dns_record.mail_dmarc[each.key]
  id       = "${local.mail_zone_ids[each.key]}/${each.value}"
}

# Forward A for Free's PTR: adopt an existing record if found.
# No import or new record unless one explicit opt-in is set.
import {
  for_each = var.home_dns_a_record_id != "" ? { "home.albandrieu.com" = var.home_dns_a_record_id } : {}
  to       = cloudflare_dns_record.home[each.key]
  id       = "${var.zone_id}/${each.value}"
}

# Zone singleton: adopt the dashboard Managed Transforms, never create them.
import {
  to = cloudflare_managed_transforms.albandrieu
  id = var.zone_id
}

# Route Access applications created in the dashboard: adopt them (22/11/2026).
import {
  for_each = var.route_access_application_ids
  to       = cloudflare_zero_trust_access_application.route[each.key]
  id       = "accounts/${var.account_id}/${each.value}"
}
