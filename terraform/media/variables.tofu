variable "radarr_url" {
  description = "Radarr URL reachable from the operator workstation (LAN Traefik)."
  type        = string
  default     = "https://radarr.int.albandrieu.com"
}

variable "sonarr_url" {
  description = "Sonarr URL reachable from the operator workstation (LAN Traefik)."
  type        = string
  default     = "https://sonarr.int.albandrieu.com"
}

variable "prowlarr_url" {
  description = "Prowlarr URL reachable from the operator workstation (LAN Traefik)."
  type        = string
  default     = "https://prowlarr.int.albandrieu.com"
}

variable "radarr_api_key" {
  description = "Radarr API key that Prowlarr uses for Full Sync (same value as RADARR_API_KEY)."
  type        = string
  sensitive   = true
}

variable "sonarr_api_key" {
  description = "Sonarr API key that Prowlarr uses for Full Sync (same value as SONARR_API_KEY)."
  type        = string
  sensitive   = true
}

variable "qbittorrent_username" {
  description = "qBittorrent WebUI user used by Radarr and Sonarr."
  type        = string
  default     = "admin"
}

variable "qbittorrent_password" {
  description = "qBittorrent WebUI password used by Radarr and Sonarr (Vaultwarden)."
  type        = string
  sensitive   = true
}

variable "lidarr_api_key" {
  description = "Lidarr API key that Prowlarr uses for Full Sync (same value as LIDARR_API_KEY)."
  type        = string
  sensitive   = true
}
