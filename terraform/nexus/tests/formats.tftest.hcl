# Offline: the pilot default must plan APT only, never realms, roles or users.
mock_provider "sonatyperepo" {}

# The mock provider never authenticates: no credential, not even a fake one.
variables {
  nexus_url      = "https://nexus.invalid"
  nexus_username = ""
  nexus_password = ""
}

run "default_is_apt_only" {
  command = plan

  assert {
    condition     = length(sonatyperepo_repository_apt_proxy.apt_proxy) == 7
    error_message = "the default plan must create the APT proxies"
  }

  assert {
    condition = alltrue([
      length(sonatyperepo_repository_npm_group.npm_group) == 0,
      length(sonatyperepo_repository_pypi_group.pypi_group) == 0,
      length(sonatyperepo_repository_docker_proxy.docker_proxy) == 0,
      length(sonatyperepo_repository_docker_group.docker_group) == 0,
      length(sonatyperepo_repository_huggingface_proxy.huggingface_proxy) == 0,
      length(sonatyperepo_repository_terraform_proxy.terraform_proxy) == 0,
    ])
    error_message = "formats outside enabled_formats must stay out of the plan"
  }

  assert {
    condition     = length(sonatyperepo_security_realms.realms) == 0 && length(sonatyperepo_user.albandrieu) == 0 && length(sonatyperepo_role.global_readwrite) == 0
    error_message = "realms, roles and users must stay unmanaged by default"
  }
}

run "npm_widens_one_format" {
  command = plan

  variables {
    enabled_formats = ["apt", "npm"]
  }

  assert {
    condition     = length(sonatyperepo_repository_npm_group.npm_group) == 1 && length(sonatyperepo_repository_pypi_group.pypi_group) == 0
    error_message = "enabling npm must not enable pypi"
  }
}

run "unknown_format_is_rejected" {
  command = plan

  variables {
    enabled_formats = ["apt", "maven"]
  }

  expect_failures = [var.enabled_formats]
}
