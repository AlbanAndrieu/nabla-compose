terraform {
  required_version = ">= 1.8.0"

  required_providers {
    vercel = {
      source  = "vercel/vercel"
      version = "= 3.15.3"
    }
  }
}

provider "vercel" {
  # Authentication: VERCEL_API_TOKEN (never commit credentials).
}
