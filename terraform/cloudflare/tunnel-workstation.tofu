# Workstation tunnel nabla-albandrieu (config_src=cloudflare), adopted from the
# dashboard on 14/11/2026. Like tunnel.tofu, this resource replaces the WHOLE
# ingress of its tunnel: a route missing here is deleted at apply, together
# with its CNAME. Never point it at the shared homelab tunnel.

locals {
  workstation_tunnel_ingress = [
    {
      hostname       = "honeypot-albandrieu.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.57:3000"
    },
    {
      hostname       = "nexus-albandrieu.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.57:8081"
    },
    {
      hostname       = "localai-gpu-albandrieu.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.57:8083"
    },
    {
      hostname       = "ollama-gpu-albandrieu.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.57:11434"
    },
    {
      hostname       = "netalertx-albandrieu.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.57:20211"
    },
    {
      hostname       = "famp-albandrieu.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.57:8082"
    },
    {
      hostname       = "ntopng-albandrieu.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.57:4000"
    },
    {
      hostname       = "anythingllm-albandrieu.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.57:1111"
    },
    {
      hostname       = "plumber-albandrieu.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.57:3001"
    },
    # plumber-api-albandrieu (live: 172.17.0.57:3003) moved to the homelab
    # tunnel on 13/11/2026 (tunnel.tofu): the first apply drops it here.
    {
      hostname       = "portracker-albandrieu.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.57:4999"
    },
    {
      hostname       = "vaultwarden-albandrieu.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.57:8007"
    },
    # Routed but never published: no public CNAME exists (dns-policy.yaml).
    {
      hostname       = "stirling-albandrieu.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.57:30124"
    },
    {
      hostname       = "motion-albandrieu.albandrieu.com"
      origin_request = {}
      service        = "http://172.17.0.57:8078"
    },
    # The dashboard stored explicit zeros on the catch-all; these attributes
    # are not computed, so omitting them would show as drift.
    {
      origin_request = {
        connect_timeout        = 0
        keep_alive_connections = 0
        keep_alive_timeout     = 0
        tcp_keep_alive         = 0
        tls_timeout            = 0
      }
      service = "http_status:503"
    },
  ]

  workstation_tunnel_hostnames = toset([
    for rule in local.workstation_tunnel_ingress : rule.hostname
    if try(rule.hostname, null) != null
    && !contains(local.dns_policy.unpublished_tunnel_hostnames, rule.hostname)
  ])
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "workstation" {
  account_id = var.account_id
  config = {
    ingress = local.workstation_tunnel_ingress
  }
  source    = "cloudflare"
  tunnel_id = var.workstation_tunnel_id

  lifecycle {
    prevent_destroy = true
  }
}

module "workstation_dns_records" {
  source = "./modules/dns-records"

  zone_id              = var.zone_id
  tunnel_target        = "${var.workstation_tunnel_id}.cfargotunnel.com"
  tunnel_hostnames     = local.workstation_tunnel_hostnames
  tunnel_record_ids    = var.dns_tunnel_record_ids
  new_tunnel_hostnames = local.dns_policy.new_tunnel_hostnames

  # A route must exist before its name is published.
  depends_on = [cloudflare_zero_trust_tunnel_cloudflared_config.workstation]
}

check "tunnels_do_not_share_hostnames" {
  assert {
    condition     = length(setintersection(local.tunnel_hostnames, local.workstation_tunnel_hostnames)) == 0
    error_message = "A hostname is routed by both the homelab and the workstation tunnel: its CNAME can only target one."
  }
}
