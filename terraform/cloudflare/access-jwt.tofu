# "Protect with Access" on the tunnel ingress: cloudflared itself verifies the
# Access JWT (signature, expiry, AUD of the route's application) and answers 403
# otherwise, so a route whose Access app is missing, deleted or misconfigured
# fails closed instead of going public.
# Not on bypass hostnames (no JWT is issued): keycloak, login, joplin, n8n
# (Slack OAuth callback), vaultwarden, fastapi-sample (GitHub webhook).

locals {
  access_team_name = "albandrieu"

  access_jwt_aud = {
    "heimdall.albandrieu.com"               = cloudflare_zero_trust_access_application.route["heimdall"].aud
    "truenas.albandrieu.com"                = cloudflare_zero_trust_access_application.truenas_admin.aud
    "prometheus.albandrieu.com"             = cloudflare_zero_trust_access_application.route["prometheus"].aud
    "scrutiny.albandrieu.com"               = cloudflare_zero_trust_access_application.route["scrutiny"].aud
    "ittools.albandrieu.com"                = cloudflare_zero_trust_access_application.route["ittools"].aud
    "uptime-kuma.albandrieu.com"            = cloudflare_zero_trust_access_application.route["uptime-kuma"].aud
    "2fauth.albandrieu.com"                 = cloudflare_zero_trust_access_application.route["2fauth"].aud
    "grafana.albandrieu.com"                = cloudflare_zero_trust_access_application.route["grafana"].aud
    "homarr.albandrieu.com"                 = cloudflare_zero_trust_access_application.route["homarr"].aud
    "gatus.albandrieu.com"                  = cloudflare_zero_trust_access_application.route["gatus"].aud
    "affine.albandrieu.com"                 = cloudflare_zero_trust_access_application.affine.aud
    "karakeep.albandrieu.com"               = cloudflare_zero_trust_access_application.route["karakeep"].aud
    "immich.albandrieu.com"                 = cloudflare_zero_trust_access_application.immich.aud
    "ha.albandrieu.com"                     = cloudflare_zero_trust_access_application.ha.aud
    "searxng.albandrieu.com"                = cloudflare_zero_trust_access_application.route["searxng"].aud
    "openwebui.albandrieu.com"              = cloudflare_zero_trust_access_application.route["openwebui"].aud
    "open-webui.albandrieu.com"             = cloudflare_zero_trust_access_application.route["openwebui"].aud
    "freshrss.albandrieu.com"               = cloudflare_zero_trust_access_application.freshrss.aud
    "reactive.albandrieu.com"               = cloudflare_zero_trust_access_application.route["reactive"].aud
    "plumber-api-albandrieu.albandrieu.com" = cloudflare_zero_trust_access_application.plumber_api.aud
    "nginx.albandrieu.com"                  = cloudflare_zero_trust_access_application.route["nginx"].aud
    "code.albandrieu.com"                   = cloudflare_zero_trust_access_application.route["code"].aud
    "cadvisor.albandrieu.com"               = cloudflare_zero_trust_access_application.route["cadvisor"].aud
    "npmplus.albandrieu.com"                = cloudflare_zero_trust_access_application.route["npmplus"].aud
    "nexus.albandrieu.com"                  = cloudflare_zero_trust_access_application.route["nexus"].aud
    "npm.albandrieu.com"                    = cloudflare_zero_trust_access_application.route["npm"].aud
    "ddns-updater.albandrieu.com"           = cloudflare_zero_trust_access_application.route["ddns-updater"].aud
    "minio.albandrieu.com"                  = cloudflare_zero_trust_access_application.route["minio"].aud
    "langfuse.albandrieu.com"               = cloudflare_zero_trust_access_application.route["langfuse"].aud
    "clickhouse.albandrieu.com"             = cloudflare_zero_trust_access_application.route["clickhouse"].aud
    "languagetool.albandrieu.com"           = cloudflare_zero_trust_access_application.route["languagetool"].aud
    "openrag.albandrieu.com"                = cloudflare_zero_trust_access_application.route["openrag"].aud
    "garage.albandrieu.com"                 = cloudflare_zero_trust_access_application.route["garage"].aud
  }

  access_jwt = {
    for host, aud in local.access_jwt_aud : host => {
      required  = true
      team_name = local.access_team_name
      aud_tag   = [aud]
    }
  }
}
