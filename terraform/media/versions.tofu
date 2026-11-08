terraform {
  required_version = ">= 1.10.0"

  required_providers {
    radarr = {
      source  = "devopsarr/radarr"
      version = "= 2.5.0"
    }
    sonarr = {
      source  = "devopsarr/sonarr"
      version = "= 3.5.0"
    }
    prowlarr = {
      source  = "devopsarr/prowlarr"
      version = "= 3.2.2"
    }
  }
}

# API keys come only from the operator process: RADARR_API_KEY,
# SONARR_API_KEY and PROWLARR_API_KEY (Vaultwarden), never from a file.
provider "radarr" {
  url = var.radarr_url
}

provider "sonarr" {
  url = var.sonarr_url
}

provider "prowlarr" {
  url = var.prowlarr_url
}
