include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = find_in_parent_folders("terraform/truenas")
}

inputs = {
  enabled                      = tobool(get_env("TRUENAS_ENABLED", "false"))
  truenas_url                  = get_env("TRUENAS_URL", "")
  truenas_username             = get_env("TRUENAS_USER", "")
  truenas_api_key              = get_env("TRUENAS_API_KEY", "")
  truenas_read_only            = tobool(get_env("TRUENAS_READ_ONLY", "true"))
  truenas_destroy_protection   = tobool(get_env("TRUENAS_DESTROY_PROTECTION", "true"))
  truenas_insecure_skip_verify = tobool(get_env("TRUENAS_INSECURE_SKIP_VERIFY", "false"))
  truenas_pool                 = get_env("TRUENAS_POOL", "")
  vm_bridge                    = get_env("TRUENAS_VM_BRIDGE", "br0")
  talos_iso_path               = get_env("TALOS_ISO_PATH", "")
}
