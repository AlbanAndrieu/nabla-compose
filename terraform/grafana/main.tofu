terraform {
  required_version = ">= 1.10.0"

  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "= 4.53.0"
    }
  }
}

# Admin basic auth comes from the operator process only: GRAFANA_AUTH=admin:<password>,
# read from Vaultwarden by scripts/grafana/mcp-identity.sh. Never a tfvar.
provider "grafana" {
  url = var.grafana_url
}

# Read-only identity of the Grafana MCP (mcp-grafana --disable-write). Its token
# is minted by scripts/grafana/mcp-identity.sh straight into Vaultwarden, so no
# secret ever lands in the OpenTofu state.
resource "grafana_service_account" "mcp_readonly" {
  name        = "mcp-readonly"
  role        = "Viewer"
  is_disabled = false
}

output "mcp_readonly_service_account_id" {
  description = "Service account id used by scripts/grafana/mcp-identity.sh (not a secret)."
  value       = grafana_service_account.mcp_readonly.id
}
