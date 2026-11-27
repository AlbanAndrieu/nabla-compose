include "root" { path = find_in_parent_folders("root.hcl") }

terraform { source = find_in_parent_folders("terraform/nexus") }
inputs = {
  # LAN route: the provider cannot send Cloudflare Access headers to nexus.albandrieu.com.
  nexus_url      = get_env("NEXUS_URL", "https://nexus.int.albandrieu.com")
  nexus_username = get_env("NEXUS_USERNAME", "")
  nexus_password = get_env("NEXUS_PASSWORD", "")
  # Applied 27/11/2026 (N1-N3): dropping a format destroys its repositories.
  # An exported TF_VAR_enabled_formats still wins: Terragrunt never overrides an existing TF_VAR_*.
  enabled_formats = ["apt", "npm", "pypi"]
}
