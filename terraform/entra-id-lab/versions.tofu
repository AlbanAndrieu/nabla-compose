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
}
