terraform {
  required_providers {
    truenas = {
      source  = "PjSalty/truenas"
      version = "~> 2.4"
    }
  }
}

provider "truenas" {
  url                  = var.truenas_url
  username             = var.truenas_username
  api_key              = var.truenas_api_key
  read_only            = var.truenas_read_only
  destroy_protection   = var.truenas_destroy_protection
  insecure_skip_verify = var.truenas_insecure_skip_verify
}
