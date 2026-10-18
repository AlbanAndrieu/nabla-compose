terraform {
  required_version = ">= 1.10.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "= 5.28.0"
    }
  }
}

# Authentication uses CLOUDFLARE_API_TOKEN from a trusted operator environment.
# Never put an API token in a tfvar, provider block or public CI secret.
provider "cloudflare" {}

locals {
  ops_hostname = "ops.albandrieu.com"
  tunnel_id    = var.manage_dedicated_tunnel ? cloudflare_zero_trust_tunnel_cloudflared.ops[0].id : var.dedicated_tunnel_id
}

# Disabled by default. Import an existing *dedicated* tunnel into state first,
# or explicitly authorize creation of a new isolated tunnel.
resource "cloudflare_zero_trust_tunnel_cloudflared" "ops" {
  count      = var.manage_dedicated_tunnel ? 1 : 0
  account_id = var.account_id
  name       = "nabla-ops"
  config_src = "cloudflare"

  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = var.tunnel_creation_approved
      error_message = "Tunnel creation/import must be explicitly approved after checking existing Cloudflare ownership."
    }
  }
}

# This replaces the ENTIRE ingress configuration of the named tunnel.
# Do not use a shared Cloudflare Tunnel here, even if importing its state works.
resource "cloudflare_zero_trust_tunnel_cloudflared_config" "ops" {
  count      = var.enable_ops_ingress ? 1 : 0
  account_id = var.account_id
  tunnel_id  = local.tunnel_id

  config = {
    ingress = [
      {
        hostname = local.ops_hostname
        service  = var.private_origin_https_url
        origin_request = {
          no_tls_verify = false
          access = {
            aud_tag   = [var.access_application_audience]
            team_name = var.access_team_name
            required  = true
          }
        }
      },
      {
        service = "http_status:404"
      }
    ]
  }

  lifecycle {
    prevent_destroy = true
    precondition {
      condition = (
        var.dedicated_tunnel_verified &&
        var.access_policy_verified &&
        var.fastapi_origin_jwt_verified &&
        can(regex("^https://", var.private_origin_https_url)) &&
        length(var.access_application_audience) > 0 &&
        length(var.access_team_name) > 0 &&
        length(local.tunnel_id) > 0
      )
      error_message = "Ingress requires a dedicated tunnel, verified Access policy/audience, strict HTTPS origin and FastAPI origin JWT authorization."
    }
  }
}

# Separate publication gate: Access must already reject non-owners and the
# origin must already fail closed before this CNAME can be created/imported.
resource "cloudflare_dns_record" "ops" {
  count   = var.publish_ops_dns ? 1 : 0
  zone_id = var.zone_id
  name    = "ops"
  type    = "CNAME"
  content = "${local.tunnel_id}.cfargotunnel.com"
  proxied = true
  ttl     = 1

  lifecycle {
    prevent_destroy = true
    precondition {
      condition = (
        var.enable_ops_ingress &&
        var.dedicated_tunnel_verified &&
        var.access_policy_verified &&
        var.fastapi_origin_jwt_verified &&
        var.public_site_redaction_verified &&
        length(local.tunnel_id) > 0
      )
      error_message = "DNS is forbidden until dedicated ingress, Access, JWT origin, and public-site redaction are verified."
    }
  }

  depends_on = [cloudflare_zero_trust_tunnel_cloudflared_config.ops]
}
