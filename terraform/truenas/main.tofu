terraform {
  required_providers {
    truenas = {
      source  = "PjSalty/truenas"
      version = "~> 1.10"
    }
  }
}

provider "truenas" {
  url                  = var.truenas_url
  api_key              = var.truenas_api_key
  read_only            = var.truenas_read_only
  destroy_protection   = var.truenas_destroy_protection
  insecure_skip_verify = var.truenas_insecure_skip_verify
}
