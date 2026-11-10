variable "account_id" {
  description = "Cloudflare account identifier (not a secret)."
  type        = string
  default     = "bdfe00eeee5845782ab91adfbff71ee1"
}

variable "zone_id" {
  description = "albandrieu.com zone identifier (not a secret)."
  type        = string
  default     = "015b9ec0f8674ce52b6cceb99d3adb3d"
}

# The repository is public: the operator WAN address is passed through
# TF_VAR_opentofu_token_client_ips, never committed.
variable "opentofu_token_client_ips" {
  description = "CIDRs allowed to use the OpenTofu apply token."
  type        = list(string)

  validation {
    condition     = length(var.opentofu_token_client_ips) > 0 && alltrue([for cidr in var.opentofu_token_client_ips : can(cidrhost(cidr, 0))])
    error_message = "Set TF_VAR_opentofu_token_client_ips to at least one CIDR (for example [\"203.0.113.7/32\"])."
  }
}

variable "state_passphrase" {
  description = "State/plan encryption passphrase (TF_VAR_state_passphrase, from Vaultwarden); losing it loses the state."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.state_passphrase) >= 16
    error_message = "state_passphrase must be at least 16 characters."
  }
}

variable "opentofu_token_expires_on" {
  description = "RFC 3339 expiry of the OpenTofu apply token; rotate by moving it forward."
  type        = string
  default     = "2027-05-10T00:00:00Z"
}
