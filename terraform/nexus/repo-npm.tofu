resource "sonatyperepo_repository_npm_proxy" "npm_proxy" {
  count = contains(var.enabled_formats, "npm") ? 1 : 0

  name   = "npm-proxy"
  online = true

  storage = {
    blob_store_name                = "default"
    strict_content_type_validation = true
  }

  proxy = {
    remote_url       = "https://registry.npmjs.org"
    content_max_age  = 1440
    metadata_max_age = 1440
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
}

resource "sonatyperepo_repository_npm_hosted" "npm_hosted" {
  count = contains(var.enabled_formats, "npm") ? 1 : 0

  name   = "npm-local"
  online = true

  storage = {
    blob_store_name                = "default"
    strict_content_type_validation = true
    write_policy                   = "ALLOW"
  }
}

resource "sonatyperepo_repository_npm_group" "npm_group" {
  count = contains(var.enabled_formats, "npm") ? 1 : 0

  name   = "npm-all"
  online = true

  storage = {
    blob_store_name                = "default"
    strict_content_type_validation = true
  }

  group = {
    member_names = [
      sonatyperepo_repository_npm_hosted.npm_hosted[0].name,
      sonatyperepo_repository_npm_proxy.npm_proxy[0].name,
    ]
  }
}
