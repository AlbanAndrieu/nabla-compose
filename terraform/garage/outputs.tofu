output "home_ops_backups_credentials" {
  description = "Generated Garage credentials for the home-ops-backups bucket. Import into Vaultwarden, then avoid printing this output again."
  sensitive   = true
  value = {
    endpoint          = var.garage_url
    access_key_id     = garage_key.homeops_backups_readwrite.id
    secret_access_key = garage_key.homeops_backups_readwrite.secret_access_key
  }
}
