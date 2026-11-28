include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = find_in_parent_folders("terraform/ntopng")

  # Each flow check write rewrites one shared Redis blob (checks.configset_v1):
  # three parallel writes lost one on 28/11/2026, so writes run one at a time.
  extra_arguments "serial_writes" {
    commands  = ["apply", "destroy"]
    arguments = ["-parallelism=1"]
  }
}

# TF_VAR_ntopng_token stays in the operator process: plan and apply through
# scripts/ntopng/control.sh, which runs scripts/infra/terragrunt-safe.sh.
inputs = {
  ntopng_url = "http://172.17.0.24:31080"
}
