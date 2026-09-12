output "discovered_repositories" {
  description = "Read-only repository inventory when github_inventory_enabled is true."
  value       = var.github_inventory_enabled ? data.github_repositories.owned[0].names : []
}

output "configured_repositories" {
  description = "Explicit allow-list eligible for governance once the corresponding safety switches are enabled."
  value       = sort(keys(var.repositories))
}

output "governance_enabled" {
  description = "Whether the master mutation safety switch is enabled."
  value       = var.github_governance_enabled
}
