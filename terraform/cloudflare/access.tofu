locals {
  # Reusable policies stay dashboard-managed: "nabla" is shared with other apps.
  access_policy_nabla_id                  = "beb35e5c-9eeb-4e6b-9410-572433c59e12" # gitleaks:allow
  access_policy_fastapi_sample_monitor_id = "98b72202-f5eb-4fdb-b259-fb664eb20752" # gitleaks:allow
}

resource "cloudflare_zero_trust_access_application" "fastapi_sample" {
  account_id                = var.account_id
  app_launcher_visible      = true
  auto_redirect_to_identity = false
  # The old name stays protected until the rename is accepted (README step 5).
  destinations = [
    {
      type = "public"
      uri  = "fastapi-sample.albandrieu.com"
    },
    {
      type = "public"
      uri  = "sample.albandrieu.com"
    },
    {
      cidr       = "172.17.0.24/32"
      port_range = "8091"
      type       = "private"
    },
  ]
  domain                     = "fastapi-sample.albandrieu.com"
  enable_binding_cookie      = false
  http_only_cookie_attribute = false
  name                       = "sample"
  options_preflight_bypass   = false
  policies = [
    {
      id         = local.access_policy_nabla_id
      precedence = 1
    },
    {
      id         = local.access_policy_fastapi_sample_monitor_id
      precedence = 2
    },
  ]
  session_duration = "24h"
  type             = "self_hosted"

  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_zero_trust_access_application" "fastapi_sample_api" {
  account_id                = var.account_id
  app_launcher_visible      = true
  auto_redirect_to_identity = false
  destinations = [
    {
      type = "public"
      uri  = "fastapi-sample.albandrieu.com/api"
    },
    {
      type = "public"
      uri  = "sample.albandrieu.com/api"
    },
  ]
  domain                     = "fastapi-sample.albandrieu.com/api"
  enable_binding_cookie      = false
  http_only_cookie_attribute = false
  name                       = "sample-api"
  options_preflight_bypass   = false
  policies = [
    {
      id         = local.access_policy_nabla_id
      precedence = 1
    },
  ]
  session_duration = "24h"
  type             = "self_hosted"

  lifecycle {
    prevent_destroy = true
  }
}
