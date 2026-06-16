locals {
  registries = [
    { name = "docker.io", remote_url = "https://registry-1.docker.io" },
    { name = "ghcr.io", remote_url = "https://ghcr.io" },
    { name = "gcr.io", remote_url = "https://gcr.io" },
    { name = "quay.io", remote_url = "https://quay.io" },
    { name = "mcr.microsoft.com", remote_url = "https://mcr.microsoft.com" },
    { name = "registry.k8s.io", remote_url = "https://registry.k8s.io" },
    { name = "oci.external-secrets.io", remote_url = "https://oci.external-secrets.io" }
  ]
}

resource "sonatyperepo_repository_docker_proxy" "docker_proxy" {
  for_each = { for registry in local.registries : registry.name => registry }
  name     = each.key
  online   = true

  storage = {
    blob_store_name                = "default"
    strict_content_type_validation = true
  }

  proxy = {
    remote_url       = each.value.remote_url
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

  docker_proxy = {}
  docker = {
    path_enabled     = true
    v1_enabled       = true
    force_basic_auth = false
  }
}

resource "sonatyperepo_repository_docker_hosted" "docker_hosted" {
  name   = "docker-internal"
  online = true

  storage = {
    blob_store_name                = "default"
    strict_content_type_validation = true
    write_policy                   = "ALLOW"
  }

  docker = {
    force_basic_auth = false
    v1_enabled       = false
  }
}

resource "sonatyperepo_repository_docker_group" "docker_group" {
  name   = "docker-all"
  online = true

  storage = {
    blob_store_name                = "default"
    strict_content_type_validation = true
  }

  group = {
    member_names = concat(
      [sonatyperepo_repository_docker_hosted.docker_hosted.name],
      [for registry in local.registries : sonatyperepo_repository_docker_proxy.docker_proxy[registry.name].name]
    )
  }

  docker = {
    force_basic_auth = false
    v1_enabled       = false
  }
}
