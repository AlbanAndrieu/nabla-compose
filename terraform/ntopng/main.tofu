terraform {
  required_version = ">= 1.10.0"

  required_providers {
    restapi = {
      source  = "Mastercard/restapi"
      version = "= 3.0.0"
    }
  }
}

# ntopng has no OpenTofu provider. Its REST API v2 is RPC-style (one POST per
# setting, answers wrapped in {rc, rsp}), so each object pushes its desired value
# and never diffs the server answer (ignore_all_server_changes).
# The nabla-control token reaches the provider through TF_VAR_ntopng_token, set by
# scripts/ntopng/control.sh from Vaultwarden: provider settings never reach the state.
provider "restapi" {
  uri                  = var.ntopng_url
  create_method        = "POST"
  update_method        = "POST"
  destroy_method       = "POST"
  write_returns_object = false
  headers = {
    Authorization = "Token ${var.ntopng_token}"
    Content-Type  = "application/json"
  }
}

# settings.json is shared with scripts/ntopng/control.sh, which reads every value
# back from ntopng: ignore_all_server_changes keeps OpenTofu blind to server drift.
#   - alert_preferences (section "alerts" of prefs_menu_schema.lua), key -> {value,
#     ntopng default}. max_entity_alerts: hourly housekeeping prunes each SQLite alert
#     family to 80 % of this cap; the 1,000,000 default (~700 MiB) does not fit the
#     384m and 64m tmpfs (27/11/2026).
#   - disabled_flow_checks: 99.6 % of the 524,793 flow alerts written on br0 in
#     12 minutes on 22/11/2026.
locals {
  settings             = jsondecode(file("${path.module}/settings.json"))
  alert_preferences    = local.settings.alert_preferences
  disabled_flow_checks = toset(local.settings.disabled_flow_checks)
}

resource "restapi_object" "alert_preference" {
  for_each = local.alert_preferences

  path         = "/lua/rest/v2/set/ntopng/preferences.lua"
  read_path    = "/lua/rest/v2/get/ntopng/get_preferences.lua"
  update_path  = "/lua/rest/v2/set/ntopng/preferences.lua"
  destroy_path = "/lua/rest/v2/set/ntopng/preferences.lua"
  object_id    = each.key
  data         = jsonencode({ pref_section = "alerts", pref_key = each.key, pref_value = each.value.value })
  # Destroying the resource restores the ntopng default.
  destroy_data = jsonencode({ pref_section = "alerts", pref_key = each.key, pref_value = each.value.default })

  ignore_all_server_changes = true
}

resource "restapi_object" "disabled_flow_check" {
  for_each = local.disabled_flow_checks

  path         = "/lua/rest/v2/disable/check.lua"
  read_path    = "/lua/rest/v2/get/checks/check_config.lua?check_subdir=flow&script_key={id}"
  update_path  = "/lua/rest/v2/disable/check.lua"
  destroy_path = "/lua/rest/v2/enable/check.lua"
  object_id    = each.key
  data         = jsonencode({ check_subdir = "flow", script_key = each.key })
  destroy_data = jsonencode({ check_subdir = "flow", script_key = each.key })

  ignore_all_server_changes = true
}
