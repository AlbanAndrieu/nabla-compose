include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = find_in_parent_folders("terraform/ntopng")
}

# TF_VAR_ntopng_token stays in the operator process: plan and apply through
# scripts/ntopng/control.sh, which runs scripts/infra/terragrunt-safe.sh.
inputs = {
  ntopng_url = "http://172.17.0.24:31080"
}
