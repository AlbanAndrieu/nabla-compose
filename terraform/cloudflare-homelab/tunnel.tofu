# Replaces the WHOLE ingress of the shared tunnel: a route missing here is
# deleted at apply. Keep every hostname and the final http_status:404 rule.

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "homelab" {
  account_id = var.account_id
  config = {
    ingress = [
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
        hostname       = "domain-watchdog.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30317"
      },
      {
        hostname       = "prometheus.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:9090"
      },
      {
        hostname       = "portracker.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30233"
      },
      {
        hostname       = "open-speed-test.albandrieu.com"
        origin_request = {}
        service        = "https://172.17.0.24:30117"
      },
      {
        hostname       = "portainer.albandrieu.com"
        origin_request = {}
        service        = "https://172.17.0.24:31015"
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
        hostname       = "localai.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30286"
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
      {
        hostname       = "keycloak.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30238"
      },
      {
        hostname       = "clamav.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:3310"
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
        hostname       = "paperless-ai.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30226"
      },
      {
        hostname       = "transmission.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30096"
      },
      {
        hostname       = "sonarr.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30113"
      },
      {
        hostname       = "radarr.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30025"
      },
      {
        hostname       = "lidarr.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30071"
      },
      {
        hostname       = "prowlarr.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30050"
      },
      {
        hostname       = "paperless-ngx.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30070"
      },
      {
        hostname       = "netbootxyz.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:31010"
      },
      {
        hostname       = "affine.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30169"
      },
      {
        hostname       = "convertx.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30154"
      },
      {
        hostname       = "bichon.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:15630"
      },
      {
        hostname       = "openarchiver.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30288"
      },
      {
        hostname       = "pgadmin.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30056"
      },
      {
        hostname       = "postgres.albandrieu.com"
        origin_request = {}
        service        = "tcp://172.17.0.24:5432"
      },
      {
        hostname       = "karakeep.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30147"
      },
      {
        hostname       = "sabnzbd.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30055"
      },
      {
        hostname       = "stirling.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30124"
      },
      {
        hostname       = "immich.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30041"
      },
      {
        hostname       = "emby.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:8096"
      },
      {
        hostname       = "ha.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30103"
      },
      {
        hostname       = "speedtest.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30220"
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
        hostname       = "anythingllm.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:30318"
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
        hostname       = "litellm.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:4000"
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
        hostname       = "kibana.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:5601"
      },
      {
        hostname       = "sample.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:8091"
      },
      {
        hostname       = "openrag.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:31060"
      },
      {
        hostname       = "garage-admin.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:3909"
      },
      {
        hostname       = "garage.albandrieu.com"
        origin_request = {}
        service        = "http://172.17.0.24:3900"
      },
      {
        service = "http_status:404"
      },
    ]
  }
  source    = "cloudflare"
  tunnel_id = var.tunnel_id

  lifecycle {
    prevent_destroy = true
  }
}
