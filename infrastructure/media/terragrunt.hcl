include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = find_in_parent_folders("terraform/media")
}

# Garage state is inherited from root.hcl. Secrets come from the operator
# process only (Vaultwarden): RADARR_API_KEY, SONARR_API_KEY, LIDARR_API_KEY, PROWLARR_API_KEY
# and QBITTORRENT_WEBUI_PASSWORD. Plan/apply only through
# scripts/infra/terragrunt-safe.sh from the LAN, never from CI.
inputs = {
  radarr_api_key       = get_env("RADARR_API_KEY", "")
  sonarr_api_key       = get_env("SONARR_API_KEY", "")
  lidarr_api_key       = get_env("LIDARR_API_KEY", "")
  qbittorrent_username = get_env("QBITTORRENT_WEBUI_USERNAME", "admin")
  qbittorrent_password = get_env("QBITTORRENT_WEBUI_PASSWORD", "")
}
