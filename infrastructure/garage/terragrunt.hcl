include "root" { path = find_in_parent_folders("root.hcl") }

terraform { source = find_in_parent_folders("terraform/garage") }
inputs = {
  garage_url    = "https://garage-admin.int.albandrieu.com"
  garage_token  = get_env("GARAGE_ADMIN_TOKEN", "")
  op_vault_name = "Automation"
}
