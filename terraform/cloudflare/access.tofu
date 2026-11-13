locals {
  # Reusable policies stay dashboard-managed: "nabla" is shared with other apps.
  access_policy_nabla_id                  = "beb35e5c-9eeb-4e6b-9410-572433c59e12" # gitleaks:allow
  access_policy_fastapi_sample_monitor_id = "98b72202-f5eb-4fdb-b259-fb664eb20752" # gitleaks:allow
  access_policy_everyone_bypass_id        = "5f5d0275-01eb-4a76-aaff-dee444b5fa54" # gitleaks:allow
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
  name                       = "fastapi-sample"
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
  name                       = "fastapi-sample-api"
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

# The account answers 403 "error code: 1050" for tunnel hostnames without an
# Access app, so public endpoints need an explicit bypass app.

# OIDC clients and browsers must reach the nabla realm without an Access login;
# /realms/master and every other path keep the default deny.
resource "cloudflare_zero_trust_access_application" "keycloak_oidc" {
  account_id           = var.account_id
  app_launcher_visible = false
  destinations = [
    {
      type = "public"
      uri  = "keycloak.albandrieu.com/realms/nabla"
    },
    {
      type = "public"
      uri  = "keycloak.albandrieu.com/resources"
    },
  ]
  domain = "keycloak.albandrieu.com/realms/nabla"
  name   = "keycloakoidc"
  policies = [
    {
      id         = local.access_policy_everyone_bypass_id
      precedence = 1
    },
  ]
  session_duration = "24h"
  type             = "self_hosted"

  lifecycle {
    prevent_destroy = true
  }
}

# The dashboard-managed "vaultwarden" app bypasses Access on the whole host for
# Bitwarden clients; this more specific path keeps /admin behind the nabla policy.
resource "cloudflare_zero_trust_access_application" "vaultwarden_admin" {
  account_id           = var.account_id
  app_launcher_visible = false
  destinations = [
    {
      type = "public"
      uri  = "vaultwarden.albandrieu.com/admin"
    },
  ]
  domain = "vaultwarden.albandrieu.com/admin"
  name   = "vaultwardenadmin"
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

# Joplin sync clients cannot complete an interactive Access login: Joplin's own
# authentication protects the server (roadmap decision, 10/11/2026).
resource "cloudflare_zero_trust_access_application" "joplin" {
  account_id           = var.account_id
  app_launcher_visible = false
  destinations = [
    {
      type = "public"
      uri  = "joplin.albandrieu.com"
    },
  ]
  domain = "joplin.albandrieu.com"
  name   = "joplin"
  policies = [
    {
      id         = local.access_policy_everyone_bypass_id
      precedence = 1
    },
  ]
  session_duration = "24h"
  type             = "self_hosted"

  lifecycle {
    prevent_destroy = true
  }
}
