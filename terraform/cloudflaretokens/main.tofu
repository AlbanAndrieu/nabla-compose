terraform {
  required_version = ">= 1.10.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "= 5.28.1"
    }
  }

  # The token value is persisted in state and CI holds a Garage key: encrypt
  # state and plans client-side with an operator-only passphrase.
  encryption {
    key_provider "pbkdf2" "operator" {
      passphrase = var.state_passphrase
    }
    method "aes_gcm" "operator" {
      keys = key_provider.pbkdf2.operator
    }
    state {
      method   = method.aes_gcm.operator
      enforced = true
    }
    plan {
      method   = method.aes_gcm.operator
      enforced = true
    }
  }
}

# Authentication comes from the operator process only (a token allowed to manage
# account API tokens). Never put a credential in a tfvar, provider block or CI.
provider "cloudflare" {}
