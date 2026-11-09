# Wiring of the *arr media stack (docs/arr-media-library-roadmap.md):
# root folders on the shared /data dataset, qBittorrent through the Gluetun
# namespace and Prowlarr Full Sync. Container-to-container URLs use the
# shared "media" Docker network.

locals {
  # Inside the media network: qBittorrent answers on its Gluetun namespace.
  qbittorrent_host = "gluetun"
  qbittorrent_port = 8080
}

resource "radarr_root_folder" "movies" {
  path = "/data/library/movies"
}

resource "sonarr_root_folder" "tv" {
  path = "/data/library/tv"
}

# Completed torrents keep seeding: Radarr/Sonarr hardlink them into the
# library instead of removing them from qBittorrent.
resource "radarr_download_client_qbittorrent" "qbittorrent" {
  name                       = "qBittorrent"
  enable                     = true
  priority                   = 1
  host                       = local.qbittorrent_host
  port                       = local.qbittorrent_port
  use_ssl                    = false
  username                   = var.qbittorrent_username
  password                   = var.qbittorrent_password
  movie_category             = "movies"
  remove_completed_downloads = false
  remove_failed_downloads    = true
}

resource "sonarr_download_client_qbittorrent" "qbittorrent" {
  name                       = "qBittorrent"
  enable                     = true
  priority                   = 1
  host                       = local.qbittorrent_host
  port                       = local.qbittorrent_port
  use_ssl                    = false
  username                   = var.qbittorrent_username
  password                   = var.qbittorrent_password
  tv_category                = "tv"
  remove_completed_downloads = false
  remove_failed_downloads    = true
}

# Prowlarr pushes indexers to the managers; their searches and .torrent
# downloads then go through Prowlarr, hence through the Gluetun HTTP proxy.
resource "prowlarr_application_radarr" "radarr" {
  name         = "Radarr"
  sync_level   = "fullSync"
  prowlarr_url = "http://prowlarr:9696"
  base_url     = "http://radarr:7878"
  api_key      = var.radarr_api_key
}

resource "prowlarr_application_sonarr" "sonarr" {
  name         = "Sonarr"
  sync_level   = "fullSync"
  prowlarr_url = "http://prowlarr:9696"
  base_url     = "http://sonarr:8989"
  api_key      = var.sonarr_api_key
}

# Lidarr's own provider is unmaintained (last release 2024): only its Prowlarr
# side is declared here; the rest is reconciled by
# scripts/media/reconcile-media-settings.py.
resource "prowlarr_application_lidarr" "lidarr" {
  name         = "Lidarr"
  sync_level   = "fullSync"
  prowlarr_url = "http://prowlarr:9696"
  base_url     = "http://lidarr:8686"
  api_key      = var.lidarr_api_key
}
