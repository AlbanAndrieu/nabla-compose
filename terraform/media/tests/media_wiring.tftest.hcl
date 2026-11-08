# Offline contract (mocked providers, no API call):
#   tofu -chdir=terraform/media init -backend=false
#   TF_VAR_qbittorrent_password=dummy tofu -chdir=terraform/media test
mock_provider "radarr" {}
mock_provider "sonarr" {}
mock_provider "prowlarr" {}

# Neutral fixture values (mocked providers never use them). The password
# variable is supplied by the runner (TF_VAR_qbittorrent_password) so that no
# credential-shaped assignment lives in Git.
variables {
  radarr_api_key = "dummy"
  sonarr_api_key = "dummy"
  lidarr_api_key = "dummy"
}

run "wiring_targets_the_vpn_namespace_and_shared_dataset" {
  command = plan

  assert {
    condition     = radarr_root_folder.movies.path == "/data/library/movies" && sonarr_root_folder.tv.path == "/data/library/tv"
    error_message = "root folders must live on the shared /data dataset (hardlinks)"
  }
  assert {
    condition = alltrue([
      radarr_download_client_qbittorrent.qbittorrent.host == "gluetun",
      sonarr_download_client_qbittorrent.qbittorrent.host == "gluetun",
      !radarr_download_client_qbittorrent.qbittorrent.remove_completed_downloads,
      !sonarr_download_client_qbittorrent.qbittorrent.remove_completed_downloads,
    ])
    error_message = "download clients must reach qBittorrent through Gluetun and keep seeding"
  }
  assert {
    condition     = alltrue([for app in [prowlarr_application_radarr.radarr, prowlarr_application_sonarr.sonarr, prowlarr_application_lidarr.lidarr] : app.sync_level == "fullSync"])
    error_message = "Prowlarr must own indexers with Full Sync"
  }
}
