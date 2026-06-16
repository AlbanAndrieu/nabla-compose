include "root" { path = find_in_parent_folders("root.hcl") }

terraform { source = find_in_parent_folders("terraform/nexus") }
inputs = {
  nexus_url      = "https://nexus.albandrieu.com"
  nexus_username = get_env("NEXUS_USERNAME", "")
  nexus_password = get_env("NEXUS_PASSWORD", "")
  op_vault_name  = "Automation"
}
