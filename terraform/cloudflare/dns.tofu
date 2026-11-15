resource "cloudflare_dns_record" "fastapi_sample" {
  content                 = "${var.tunnel_id}.cfargotunnel.com"
  include_shadow_metadata = false
  name                    = "fastapi-sample.albandrieu.com"
  proxied                 = true
  settings = {
    flatten_cname = false
    ipv4_only     = false
    ipv6_only     = false
  }
  tags    = []
  ttl     = 1
  type    = "CNAME"
  zone_id = var.zone_id

  # Access must protect a hostname before DNS publishes it.
  depends_on = [
    cloudflare_zero_trust_access_application.fastapi_sample,
    cloudflare_zero_trust_access_application.fastapi_sample_api,
  ]

  lifecycle {
    prevent_destroy = true
  }
}

# Forward DNS required before Free can configure the reverse (PTR) for its IPv4.
# Staged safely: an existing A must be imported; creating a missing A requires
# explicit verified-absence approval. Do not put this hostname on a tunnel.
locals {
  home_dns_a_enabled = var.home_dns_a_record_id != "" || var.home_dns_a_create_approved
}

resource "cloudflare_dns_record" "home" {
  for_each = local.home_dns_a_enabled ? { "home.albandrieu.com" = "82.66.4.247" } : {}

  zone_id                 = var.zone_id
  name                    = each.key
  type                    = "A"
  content                 = each.value
  proxied                 = false
  ttl                     = 1
  include_shadow_metadata = false
  tags                    = []

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = !(var.home_dns_a_record_id != "" && var.home_dns_a_create_approved)
      error_message = "home A: choose import of an existing record OR approved creation, never both."
    }

    precondition {
      condition = (
        !contains(local.tunnel_hostnames, each.key) &&
        !contains(local.workstation_tunnel_hostnames, each.key)
      )
      error_message = "home.albandrieu.com must be direct DNS-only, not a Cloudflare Tunnel hostname."
    }
  }
}
