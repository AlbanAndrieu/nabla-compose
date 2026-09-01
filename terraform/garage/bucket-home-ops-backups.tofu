resource "garage_bucket" "home_ops_backups" {
  global_alias = "home-ops-backups"
}

resource "garage_key" "homeops_backups_readwrite" {
  name = "home-ops-backups-readwrite"
}

resource "garage_bucket_permission" "readwrite" {
  bucket_id     = garage_bucket.home_ops_backups.id
  access_key_id = garage_key.homeops_backups_readwrite.id
  read          = true
  write         = true
  owner         = false
}
