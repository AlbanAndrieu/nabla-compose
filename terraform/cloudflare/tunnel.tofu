# Replaces the WHOLE ingress of the shared tunnel: a route missing here is
# deleted at apply. Keep every hostname and the final http_status:404 rule.

locals {
  # Every public hostname route of the shared tunnel. dns.tofu derives the
  # proxied CNAME of each route from this list, so a route and its DNS record
  # are always added or removed together.
  tunnel_ingress = [
    {
      hostname = "heimdall.albandrieu.com"
      origin_request = {
        no_tls_verify = true
      }
      service = "https://172.17.0.24:30120"
    },
    # TrueNAS administration: Access-protected public 443 to HTTPS LAN 7000.
    # Keep origin certificate verification and the TrueNAS hostname for SNI.
    {
      hostname = "truenas.albandrieu.com"
      origin_request = {
        origin_server_name = "truenas.albandrieu.com"
      }
      service = "https://172.17.0.24:7000"
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
    # No Keycloak App listens on :30238 (16/11) while keycloakoidc bypasses
    # Access on /realms/nabla: refuse until Keycloak runs (H01), then restore
    # http://172.17.0.24:30238 here.
    {
      hostname       = "keycloak.albandrieu.com"
      path           = "^/(realms|resources|\\.well-known)/"
      origin_request = {}
      service        = "http_status:404"
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
      hostname       = "plumber-api-albandrieu.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.24:31071"
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
      hostname = "fastapi-sample.albandrieu.com"
      # Opt-in canary; unchanged direct origin by default. SNI verifies the
      # verified private Traefik wildcard certificate while Host selects public router.
      # "traefik" resolves on cloudflared's own network (Traefik joins
      # ix-cloudflared_default), so Traefik sees cloudflared as the socket peer.
      origin_request = {
        origin_server_name = var.fastapi_sample_tunnel_via_traefik ? "traefik.int.albandrieu.com" : null
        http_host_header   = var.fastapi_sample_tunnel_via_traefik ? "fastapi-sample.albandrieu.com" : null
      }
      service = var.fastapi_sample_tunnel_via_traefik ? "https://traefik:443" : "http://172.17.0.24:8091"
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
    # Honeypot: direct :31090 remains the default, including the address
    # harvester on /. Switch to Traefik ONLY after peer-IP, TLS, AppSec, Docker
    # and access-log acceptance (honeypot runbook). Access stays Everyone bypass.
    # CNAME publishing is a separate import-first DNS plan, not a tunnel apply.
    {
      hostname = "login.albandrieu.com"
      origin_request = {
        origin_server_name = var.honeypot_tunnel_via_traefik ? "traefik.int.albandrieu.com" : null
        http_host_header   = var.honeypot_tunnel_via_traefik ? "login.albandrieu.com" : null
      }
      service = var.honeypot_tunnel_via_traefik ? "https://traefik:443" : "http://172.17.0.24:31090"
    },
    # Joplin Server (10/11): sync clients cannot complete an interactive
    # Access login, so this route relies on Joplin's own authentication, behind
    # an "Everyone bypass" Access app. No Joplin App runs yet (H08): until it
    # does, refuse at the edge so whatever binds :22300 is never published
    # unauthenticated. Restore http://172.17.0.24:22300 in the H08 deploy PR.
    {
      hostname       = "joplin.albandrieu.com"
      origin_request = {}
      service        = "http_status:404"
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
    cloudflare_zero_trust_access_application.honeypot_login,
    cloudflare_zero_trust_access_application.truenas_admin,
  ]

  lifecycle {
    prevent_destroy = true
  }
}
