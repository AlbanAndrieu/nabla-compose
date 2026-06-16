locals {
  apt_repos = [
    { name = "apt-ubuntu-24-04", remote_url = "https://archive.ubuntu.com/ubuntu/", distribution = "noble" },
    { name = "apt-ubuntu-25-04", remote_url = "https://archive.ubuntu.com/ubuntu/", distribution = "plucky" },
    { name = "apt-ubuntu-25-10", remote_url = "https://archive.ubuntu.com/ubuntu/", distribution = "questing" },
    { name = "apt-ubuntu-26-04", remote_url = "https://archive.ubuntu.com/ubuntu/", distribution = "resolute" },
    { name = "apt-debian-12", remote_url = "https://deb.debian.org/debian/", distribution = "bookworm" },
    { name = "apt-debian-13", remote_url = "https://deb.debian.org/debian/", distribution = "trixie" },
  ]
}

resource "sonatyperepo_repository_apt_proxy" "apt_proxy" {
  for_each = { for repo in local.apt_repos : repo.name => repo }

  name   = each.key
  online = true

  storage = {
    blob_store_name                = "default"
    strict_content_type_validation = true
  }

  proxy = {
    remote_url       = each.value.remote_url
    content_max_age  = 1439
    metadata_max_age = 1439
  }

  negative_cache = {
    enabled      = true
    time_to_live = 1440
  }


  http_client = {
    auto_block = false
    blocked    = false

    connection = {
      enable_circular_redirects = true
      enable_cookies            = true
      retries                   = 3
      timeout                   = 60
      use_trust_store           = false
    }
  }

  apt = {
    distribution = each.value.distribution
  }
}
