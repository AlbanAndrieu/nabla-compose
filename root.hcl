remote_state {
  backend = "s3"

  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }

  config = {
    endpoints                   = { s3 = "https://s3.nas.svc.h.albandrieu.com" }
    bucket                      = "tfstate-truenas-apps"
    key                         = "${replace(path_relative_to_include(), "infrastructure/", "")}/tfstate.json"
    region                      = "us-east-1"
    use_lockfile                = true
    skip_credentials_validation = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    use_path_style              = true
  }
}
