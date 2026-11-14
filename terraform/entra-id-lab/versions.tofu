terraform {
  required_version = ">= 1.8.0"
  required_providers {
    azuread = {
      source  = "hashicorp/azuread"
      version = "= 3.10.0"
    }
  }
}
provider "azuread" {
  tenant_id = var.tenant_id
  use_oidc  = var.ci_use_oidc
  use_cli   = !var.ci_use_oidc
  client_id = var.ci_use_oidc ? var.ci_graph_client_id : null
}
