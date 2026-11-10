include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = find_in_parent_folders("terraform/cloudflaretokens")
}

# Separate state: only this unit needs the "Account API Tokens" permission.
# The bootstrap credential and TF_VAR_opentofu_token_client_ips stay in the
# operator process. Apply only through scripts/infra/terragrunt-safe.sh after a
# reviewed plan; never from CI.
