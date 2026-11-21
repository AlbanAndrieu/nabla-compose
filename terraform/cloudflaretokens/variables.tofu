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

variable "albanandrieu_zone_id" {
  description = "albanandrieu.com zone identifier (not a secret); mail records of terraform/cloudflare only."
  type        = string
  default     = "227e423f0194d42016dd753d4a23437f"
}

variable "mail_zone_ids" {
  description = "The 18 other zones of the account (not secrets), mail records of terraform/cloudflare/mail.tofu only; same map as its mail-record-ids.auto.tfvars."
  type        = map(string)
  default = {
    "bababou.com"  = "61e2a1b07b61809660ad83963e0dbfd7" # gitleaks:allow
    "bababou.net"  = "48c393f5dffe3a739bf5fa81d99e04e2" # gitleaks:allow
    "dr-alban.com" = "6c5ccf0f43895850f2262065b664ab72" # gitleaks:allow
    "eokoo.net"    = "07ca4cfe51a5b10def541febe5ac1ace" # gitleaks:allow
    "eokou.com"    = "9427a9c671638c8249c8f8c090362058" # gitleaks:allow
    "heoko.com"    = "648218864bdc5fdf92b73840a544def9" # gitleaks:allow
    "heoko.net"    = "e4e96ff74d4f12eaf0c30e03d364175c" # gitleaks:allow
    "heoko.org"    = "06a2809d003c34336d76bb402cb93b07" # gitleaks:allow
    "heokoo.com"   = "078c0f7f56ca145ef89b6a4388714b7d" # gitleaks:allow
    "heokoo.net"   = "12a862545b7c573bedb6fa28027ab905" # gitleaks:allow
    "heokoo.org"   = "6d03cc839c5802d93a55c45db801ff84" # gitleaks:allow
    "heokou.com"   = "47014dfc9c86ab81020f62f493f4eba7" # gitleaks:allow
    "heokou.net"   = "06062693b866586d19c301030fc04aa7" # gitleaks:allow
    "heokou.org"   = "54792692fe4c1fdaa3e530ce178f8534" # gitleaks:allow
    "papapou.com"  = "c09a7fad9b8c2ad7ce8aeb746265561b" # gitleaks:allow
    "papapou.net"  = "2e1e665ff148873b590b847aec301b8c" # gitleaks:allow
    "papapou.org"  = "48a9ea64322b4796d05850a7709fdf9e" # gitleaks:allow
    "papoyou.net"  = "29119681fa1071f1271bd4974f02baae" # gitleaks:allow
  }
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
