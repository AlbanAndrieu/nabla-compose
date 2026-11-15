# Dedicated state: Azure Blob lease locking, not the shared Garage state.
# Pass storage_account_name/container_name via init -backend-config.
terraform {
  backend "azurerm" {
    key              = "entra-id-lab.tfstate"
    use_azuread_auth = true
  }
}
