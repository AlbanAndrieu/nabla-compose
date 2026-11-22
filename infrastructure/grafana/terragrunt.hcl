include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = find_in_parent_folders("terraform/grafana")
}

# GRAFANA_AUTH stays in the operator process; apply through
# scripts/grafana/mcp-identity.sh apply, which runs scripts/infra/terragrunt-safe.sh.
inputs = {
  grafana_url = get_env("GRAFANA_URL", "http://172.17.0.24:30037")
}
