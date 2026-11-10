terraform {
  required_version = ">= 1.10.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "= 5.28.1"
    }
  }
}

# Authentication comes from the operator process only (a token allowed to manage
# account API tokens). Never put a credential in a tfvar, provider block or CI.
provider "cloudflare" {}
