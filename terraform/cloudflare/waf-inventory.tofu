# Read-only pilot. No ruleset resources or changes to existing WAF.
variable "waf_inventory_enabled" {
  description = "Inventory existing zone WAF entrypoints before any import-first adoption."
  type        = bool
  default     = false
}

data "cloudflare_rulesets" "waf_inventory" {
  count   = var.waf_inventory_enabled ? 1 : 0
  zone_id = var.zone_id
}

locals {
  waf_phases = toset([
    "http_request_firewall_custom",
    "http_request_firewall_managed",
    "http_ratelimit",
  ])
  waf_entrypoints = var.waf_inventory_enabled ? {
    for ruleset in data.cloudflare_rulesets.waf_inventory[0].rulesets :
    ruleset.id => ruleset.phase
    if ruleset.kind == "zone" && contains(local.waf_phases, ruleset.phase)
  } : {}
}

data "cloudflare_ruleset" "waf_entrypoint" {
  for_each = local.waf_entrypoints
  zone_id  = var.zone_id
  id       = each.key
}

output "waf_inventory_summary" {
  description = "Existing zone entrypoints only; no expressions or credentials in this summary."
  value = {
    for id, ruleset in data.cloudflare_ruleset.waf_entrypoint :
    id => {
      phase         = ruleset.phase
      total_rules   = length(coalesce(ruleset.rules, []))
      enabled_rules = length([for rule in coalesce(ruleset.rules, []) : rule if rule.enabled == true])
    }
  }
}
