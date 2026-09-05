remote_state {
  backend = "s3"

  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }

  config = {
    endpoints = { s3 = get_env("GARAGE_S3_ENDPOINT", "https://s3.int.albandrieu.com") }
    bucket    = get_env("GARAGE_STATE_BUCKET", "opentofu-state")
    key       = "${replace(path_relative_to_include(), "infrastructure/", "")}/tfstate.json"
    region    = "us-east-1"

    # Garage v2.3.0 does not implement the conditional PutObject semantics
    # required by OpenTofu's native S3 lockfile. Keep the state in Garage,
    # but serialize operators with scripts/infra/terragrunt-safe.sh until a
    # distributed locking backend is introduced.
    use_lockfile                = false
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    skip_metadata_api_check     = true
    use_path_style              = true
  }
}
