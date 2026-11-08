# Public DNS as code for the hostnames this unit owns.
#
# - every tunnel route of local.tunnel_ingress gets its proxied CNAME to the
#   tunnel (fastapi-sample keeps its dedicated resource in dns.tofu);
# - retired hostnames of dns-policy.yaml are adopted, then destroyed, in two
#   reviewed plans (README "DNS as code");
# - records owned by AutoXpose, the legacy Traefik companion or DDNS stay
#   outside this unit until adopted; capture-dns-records.py inventories them.

locals {
  dns_policy = yamldecode(file("${path.module}/dns-policy.yaml"))

  # Path-scoped routes repeat a hostname (keycloak): one record per hostname.
  tunnel_hostnames = toset([
    for rule in local.tunnel_ingress : rule.hostname
    if try(rule.hostname, null) != null && rule.hostname != "fastapi-sample.albandrieu.com"
  ])
}

module "dns_records" {
  source = "./modules/dns-records"

  zone_id              = var.zone_id
  tunnel_target        = "${var.tunnel_id}.cfargotunnel.com"
  tunnel_hostnames     = local.tunnel_hostnames
  tunnel_record_ids    = var.dns_tunnel_record_ids
  new_tunnel_hostnames = local.dns_policy.new_tunnel_hostnames
  retired_hostnames    = toset(local.dns_policy.retired_hostnames)
  retired_record_ids   = var.dns_retired_record_ids
  retirement_phase     = var.dns_retirement_phase

  # A route must exist before its name is published.
  depends_on = [cloudflare_zero_trust_tunnel_cloudflared_config.homelab]
}

check "no_public_private_namespace_records" {
  data "cloudflare_dns_records" "private_namespace" {
    zone_id = var.zone_id
    name = {
      endswith = local.dns_policy.forbidden_public_suffixes[0]
    }
  }

  assert {
    condition     = length(data.cloudflare_dns_records.private_namespace.result) == 0
    error_message = "Public Cloudflare records exist under ${local.dns_policy.forbidden_public_suffixes[0]}: private-namespace drift (docs/dns-ingress-ownership.md)."
  }
}
