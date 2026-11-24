terraform {
  required_providers {
    sonatyperepo = {
      source  = "sonatype-nexus-community/sonatyperepo"
      version = "1.7.2"
    }
  }
}

provider "sonatyperepo" {
  url      = var.nexus_url
  username = var.nexus_username
  password = var.nexus_password
}
