resource "sonatyperepo_repository_terraform_proxy" "terraform_proxy" {
  name   = "terraform-proxy"
  online = true

  storage = {
    blob_store_name                = "default"
    strict_content_type_validation = true
  }

  proxy = {
    remote_url       = "https://registry.terraform.io"
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

  terraform = {
    require_authentication = false
  }
}
