terraform {
  required_providers {
    garage = {
      source  = "registry.terraform.io/jkossis/garage"
      version = "1.0.4"
    }
    onepassword = {
      source  = "1Password/onepassword"
      version = "3.3.1"
    }
  }
}

provider "garage" {
  endpoint = var.garage_url
  token    = var.garage_token
}

data "onepassword_vault" "vault" {
  name = var.op_vault_name
}
