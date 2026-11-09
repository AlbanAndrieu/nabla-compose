# Proxied CNAMEs for tunnel routes and two-phase retirement of decommissioned
# hostnames. Import blocks live in the root module (imports.tofu).

locals {
  # Keys are "<name>/<TYPE>" so one retired name may carry A and AAAA records.
  retired_records = var.retirement_phase == "adopt" ? {
    for key, id in var.retired_record_ids : key => {
      name = split("/", key)[0]
      type = split("/", key)[1]
    }
    if contains(var.retired_hostnames, split("/", key)[0])
  } : {}
}

resource "cloudflare_dns_record" "tunnel" {
  for_each = var.tunnel_hostnames

  zone_id                 = var.zone_id
  name                    = each.key
  type                    = "CNAME"
  content                 = var.tunnel_target
  proxied                 = true
  ttl                     = 1
  include_shadow_metadata = false
  settings = {
    flatten_cname = false
    ipv4_only     = false
    ipv6_only     = false
  }
  tags = []

  lifecycle {
    precondition {
      condition = (
        contains(keys(var.tunnel_record_ids), each.key)
        || contains(var.new_tunnel_hostnames, each.key)
      )
      error_message = "${each.key} has no import id: run scripts/cloudflare/capture-dns-records.py --write, or list it in new_tunnel_hostnames if the record really does not exist."
    }
    precondition {
      condition     = !contains(var.retired_hostnames, each.key)
      error_message = "${each.key} is both a tunnel route and a retired hostname."
    }
  }
}

# Import-only placeholders: never created or updated; destroyed when
# retirement_phase switches to "retire".
resource "cloudflare_dns_record" "retired" {
  for_each = local.retired_records

  zone_id = var.zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 1

  lifecycle {
    ignore_changes = all
  }
}
