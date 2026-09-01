terraform {
  required_providers {
    garage = {
      source  = "registry.terraform.io/jkossis/garage"
      version = "1.0.4"
    }
  }
}

provider "garage" {
  endpoint = var.garage_url
  token    = var.garage_token
}
