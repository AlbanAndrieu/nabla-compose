terraform {
  required_version = ">= 1.10.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "= 5.28.1"
    }
  }
}

# Authentication uses CLOUDFLARE_API_TOKEN from the operator process only.
# Never put an API token in a tfvar, provider block or CI secret.
provider "cloudflare" {}
