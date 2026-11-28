variable "ntopng_url" {
  description = "ntopng base URL on the LAN (TrueNAS host network)."
  type        = string
  default     = "http://172.17.0.24:31080"
}

variable "ntopng_token" {
  description = "API token of the ntopng administrator nabla-control (Vaultwarden nabla/prod/ntopng-control)."
  type        = string
  sensitive   = true
}
