include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = find_in_parent_folders("terraform/vercel-waf")
}

# Inherit Garage S3 state from root.hcl:
# key = vercel-waf/tfstate.json, with NO distributed S3 lock.
# Use scripts/infra/terragrunt-safe.sh for init/import/plan/apply.
# Never apply from GitHub Actions or a second workstation.
