check "enabled_configuration" {
  assert {
    condition = !var.enabled || (
      startswith(var.truenas_url, "https://") &&
      length(trimspace(var.truenas_username)) > 0 &&
      length(trimspace(var.truenas_api_key)) > 0 &&
      length(trimspace(var.truenas_pool)) > 0 &&
      length(trimspace(var.vm_bridge)) > 0
    )
    error_message = "When enabled=true, configure an HTTPS TrueNAS URL, username, API key, pool, and VM bridge before planning Talos resources."
  }
}

check "write_safety" {
  assert {
    condition     = !var.enabled || var.truenas_read_only || var.truenas_destroy_protection
    error_message = "TrueNAS write mode requires truenas_destroy_protection=true during the Talos bootstrap phase."
  }
}

check "talos_control_plane" {
  assert {
    condition     = !var.enabled || length([for name in keys(var.talos_vms) : name if startswith(lower(name), "taloscp")]) >= 1
    error_message = "The enabled Talos test topology must include at least one control-plane VM named with the taloscp prefix."
  }
}
