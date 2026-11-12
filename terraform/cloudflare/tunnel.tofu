# Replaces the WHOLE ingress of the shared tunnel: a route missing here is
# deleted at apply. Keep every hostname and the final http_status:404 rule.

locals {
  # Every public hostname route of the shared tunnel. dns.tofu derives the
  # proxied CNAME of each route from this list, so a route and its DNS record
  # are always added or removed together.
  tunnel_ingress = [
    {
      hostname       = "adguardhome.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:30004"
    },
    {
      hostname = "heimdall.albandrieu.com"
      origin_request = {
        no_tls_verify = true
      }
      service = "https://172.17.0.24:30120"
    },
    {
      hostname       = "prometheus.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:9090"
    },
    {
      hostname       = "scrutiny.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:31054"
    },
    {
      hostname       = "ittools.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:30063"
    },
    {
      hostname       = "uptime-kuma.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:31050"
    },
    {
      hostname       = "2fauth.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:30081"
    },
    {
      hostname       = "ollama.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:30068"
    },
    {
      hostname       = "n8n.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:30109"
    },
    {
      hostname       = "grafana.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:30037"
    },
    # Keycloak: publish only the production endpoints recommended by
    # https://www.keycloak.org/server/reverseproxy (OIDC realms, assets,
    # discovery). /admin/, /metrics, /health and the root stay internal.
    # The master realm is administration-only: it is refused first
    # (rules are evaluated top to bottom, the first match wins).
    {
      hostname       = "keycloak.albandrieu.com"
      path           = "^/realms/master(/|$)"
      origin_request = {}
      service        = "http_status:404"
    },
    {
      hostname       = "keycloak.albandrieu.com"
      path           = "^/(realms|resources|\\.well-known)/"
      origin_request = {}
      service        = "http://172.17.0.24:30238"
    },
    {
      hostname       = "keycloak.albandrieu.com"
      origin_request = {}
      service        = "http_status:404"
    },
    {
      hostname       = "homarr.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:30100"
    },
    {
      hostname       = "gatus.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:8085"
    },
    {
      hostname       = "affine.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:30169"
    },
    {
      hostname       = "karakeep.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:30147"
    },
    {
      hostname       = "immich.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:30041"
    },
    {
      hostname       = "ha.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:30103"
    },
    {
      hostname       = "searxng.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:30053"
    },
    {
      hostname       = "openwebui.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:31028"
    },
    {
      hostname       = "freshrss.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:30108"
    },
    {
      hostname       = "reactive.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:30393"
    },
    {
      hostname       = "traefik.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:8080"
    },
    {
      hostname       = "drawio.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:9080"
    },
    {
      hostname       = "nginx.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:8099"
    },
    {
      hostname       = "code.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:8443"
    },
    {
      hostname       = "cadvisor.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:8089"
    },
    {
      hostname       = "pihole.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:20720"
    },
    {
      hostname       = "autoxpose.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:4949"
    },
    {
      hostname       = "npmplus.albandrieu.com"
      origin_request = {}
      service        = "https://172.17.0.24:30359"
    },
    {
      hostname       = "nexus.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:8081"
    },
    {
      hostname       = "npm.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:30020"
    },
    {
      hostname       = "ddns-updater.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:8000"
    },
    {
      hostname       = "ollama-gpu.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.57:11434"
    },
    {
      hostname       = "minio.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:9091"
    },
    {
      hostname       = "langfuse.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:3000"
    },
    {
      hostname       = "clickhouse.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:8123"
    },
    {
      hostname       = "languagetool.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:8010"
    },
    {
      hostname       = "vaultwarden.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:30032"
    },
    {
      hostname       = "open-webui.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:31028"
    },
    {
      hostname       = "sentry.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:9005"
    },
    {
      hostname       = "fastapi-sample.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:8091"
    },
    {
      hostname       = "openrag.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:31060"
    },
    # Garage WebUI, not the S3 API (:3900), which must stay on s3.int (LAN).
    {
      hostname       = "garage.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:3909"
    },
    # Joplin Server (10/11): sync clients cannot complete an interactive
    # Access login, so this route relies on Joplin's own authentication.
    {
      hostname       = "joplin.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:22300"
    },
    {
      service = "http_status:404"
    },
  ]
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "homelab" {
  account_id = var.account_id
  config = {
    ingress = local.tunnel_ingress
  }
  source    = "cloudflare"
  tunnel_id = var.tunnel_id

  # Access must protect a hostname before the tunnel routes it.
  depends_on = [
    cloudflare_zero_trust_access_application.fastapi_sample,
    cloudflare_zero_trust_access_application.fastapi_sample_api,
  ]

  lifecycle {
    prevent_destroy = true
  }
}
