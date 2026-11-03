include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = find_in_parent_folders("terraform/cloudflare-homelab")
}

# Garage state is inherited from root.hcl. Identifiers come from the committed
# import-ids.auto.tfvars; CLOUDFLARE_API_TOKEN stays in the operator
# process. Apply only through scripts/infra/terragrunt-safe.sh after a reviewed
# plan; never from CI.
