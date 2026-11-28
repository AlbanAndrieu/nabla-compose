# Dashboard-created Access applications of the tunnel routes, adopted on 22/11/2026
# (import-first, see imports.tofu). Their AUD feeds the "Protect with Access" check
# of the tunnel ingress (access-jwt.tofu). Private destinations are WARP access to the LAN port.

locals {
  access_policy_temporary_access_id = "40efb9f7-a8fd-45e1-b65f-c70b473d6bed" # gitleaks:allow
  access_policy_slack_id            = "f6c5c796-92d5-4b2e-a7b3-2d92f16e8b1d" # gitleaks:allow

  route_access_applications = {
    "heimdall" = {
      domain = "heimdall.albandrieu.com"
      destinations = [
        { type = "public", uri = "heimdall.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "30120" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = ["truenas"]
    }
    "prometheus" = {
      domain = "prometheus.albandrieu.com"
      destinations = [
        { type = "public", uri = "prometheus.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "9090" },
      ]
      policies = [local.access_policy_fastapi_sample_monitor_id, local.access_policy_nabla_id]
      tags     = []
    }
    "scrutiny" = {
      domain = "scrutiny.albandrieu.com"
      destinations = [
        { type = "public", uri = "scrutiny.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "31054" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "ittools" = {
      domain = "ittools.albandrieu.com"
      destinations = [
        { type = "public", uri = "ittools.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "30063" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "uptime-kuma" = {
      domain = "uptime-kuma.albandrieu.com"
      destinations = [
        { type = "public", uri = "uptime-kuma.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "31050" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "2fauth" = {
      domain = "2fauth.albandrieu.com"
      destinations = [
        { type = "public", uri = "2fauth.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "30081" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "n8n" = {
      domain = "n8n.albandrieu.com"
      destinations = [
        { type = "public", uri = "n8n.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "30109" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "n8n-slack" = {
      domain = "n8n.albandrieu.com/rest/oauth2-credential/callback*"
      destinations = [
        { type = "public", uri = "n8n.albandrieu.com/rest/oauth2-credential/callback*", cidr = null, port_range = null },
      ]
      policies = [local.access_policy_slack_id]
      tags     = []
    }
    "grafana" = {
      domain = "grafana.albandrieu.com"
      destinations = [
        { type = "public", uri = "grafana.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "30037" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "homarr" = {
      domain = "homarr.albandrieu.com"
      destinations = [
        { type = "public", uri = "homarr.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "30100" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "gatus" = {
      domain = "gatus.albandrieu.com"
      destinations = [
        { type = "public", uri = "gatus.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "8085" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "karakeep" = {
      domain = "karakeep.albandrieu.com"
      destinations = [
        { type = "public", uri = "karakeep.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "30147" },
      ]
      policies = [local.access_policy_fastapi_sample_monitor_id, local.access_policy_nabla_id]
      tags     = []
    }
    "searxng" = {
      domain = "searxng.albandrieu.com"
      destinations = [
        { type = "public", uri = "searxng.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "30053" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "openwebui" = {
      domain = "openwebui.albandrieu.com"
      destinations = [
        { type = "public", uri = "openwebui.albandrieu.com", cidr = null, port_range = null },
        { type = "public", uri = "open-webui.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "31028" },
      ]
      # The site support chat (nabla-site-alban /api/support-chat) calls the API with its own service token.
      policies = concat(
        [local.access_policy_nabla_id, local.access_policy_temporary_access_id, local.access_policy_fastapi_sample_monitor_id],
        [for policy in cloudflare_zero_trust_access_policy.site_support : policy.id],
      )
      tags = []
    }
    "reactive" = {
      domain = "reactive.albandrieu.com"
      destinations = [
        { type = "public", uri = "reactive.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "30393" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "nginx" = {
      domain = "nginx.albandrieu.com"
      destinations = [
        { type = "public", uri = "nginx.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "8099" },
      ]
      policies = [local.access_policy_nabla_id]
      tags     = []
    }
    "code" = {
      domain = "code.albandrieu.com"
      destinations = [
        { type = "public", uri = "code.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "8443" },
      ]
      policies = [local.access_policy_nabla_id]
      tags     = []
    }
    "cadvisor" = {
      domain = "cadvisor.albandrieu.com"
      destinations = [
        { type = "public", uri = "cadvisor.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "8089" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "npmplus" = {
      domain = "npmplus.albandrieu.com"
      destinations = [
        { type = "public", uri = "npmplus.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "30359" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "nexus" = {
      domain = "nexus.albandrieu.com"
      destinations = [
        { type = "public", uri = "nexus.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "8081" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "npm" = {
      domain = "npm.albandrieu.com"
      destinations = [
        { type = "public", uri = "npm.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "30020" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "ddns-updater" = {
      domain = "ddns-updater.albandrieu.com"
      destinations = [
        { type = "public", uri = "ddns-updater.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "8000" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "minio" = {
      domain = "minio.albandrieu.com"
      destinations = [
        { type = "public", uri = "minio.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "9091" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "langfuse" = {
      domain = "langfuse.albandrieu.com"
      destinations = [
        { type = "public", uri = "langfuse.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "3000" },
      ]
      # Vercel support uses its existing scoped Access service token for OTLP and feedback.
      policies = concat(
        [local.access_policy_nabla_id, local.access_policy_temporary_access_id, local.access_policy_fastapi_sample_monitor_id],
        [for policy in cloudflare_zero_trust_access_policy.site_support : policy.id],
      )
      tags     = []
    }
    "clickhouse" = {
      domain = "clickhouse.albandrieu.com"
      destinations = [
        { type = "public", uri = "clickhouse.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "8123" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "languagetool" = {
      domain = "languagetool.albandrieu.com"
      destinations = [
        { type = "public", uri = "languagetool.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "8010" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "vaultwarden" = {
      domain = "vaultwarden.albandrieu.com"
      destinations = [
        { type = "public", uri = "vaultwarden.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "30032" },
      ]
      policies = [local.access_policy_everyone_bypass_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "openrag" = {
      domain = "openrag.albandrieu.com"
      destinations = [
        { type = "public", uri = "openrag.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "31060" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
    "garage" = {
      domain = "garage.albandrieu.com"
      destinations = [
        { type = "public", uri = "garage.albandrieu.com", cidr = null, port_range = null },
        { type = "private", uri = null, cidr = "172.17.0.24/32", port_range = "3900" },
      ]
      policies = [local.access_policy_nabla_id, local.access_policy_fastapi_sample_monitor_id]
      tags     = []
    }
  }
}

resource "cloudflare_zero_trust_access_application" "route" {
  for_each = local.route_access_applications

  account_id                = var.account_id
  app_launcher_visible      = true
  auto_redirect_to_identity = false
  destinations              = each.value.destinations
  domain                    = each.value.domain
  enable_binding_cookie     = false
  # HttpOnly CF_Authorization cookie, as on the other managed apps: scripts cannot read it.
  http_only_cookie_attribute = true
  name                       = each.key
  options_preflight_bypass   = false
  policies                   = [for i, id in each.value.policies : { id = id, precedence = i + 1 }]
  session_duration           = "24h"
  tags                       = length(each.value.tags) > 0 ? each.value.tags : null
  type                       = "self_hosted"

  lifecycle {
    prevent_destroy = true
  }
}
