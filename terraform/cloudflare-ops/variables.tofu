variable "account_id" {
  description = "Cloudflare account identifier, discovered read-only. No secrets."
  type        = string
  default     = ""
}

variable "zone_id" {
  description = "Cloudflare albandrieu.com zone identifier, discovered read-only."
  type        = string
  default     = ""
}

variable "dedicated_tunnel_id" {
  description = "Existing dedicated ops-only tunnel UUID; NEVER use the shared homelab tunnel."
  type        = string
  default     = ""
}

variable "manage_dedicated_tunnel" {
  description = "Create/import and own the dedicated tunnel resource. Off by default."
  type        = bool
  default     = false
}

variable "tunnel_creation_approved" {
  description = "Explicitly approves management of the isolated tunnel, never inferred."
  type        = bool
  default     = false
}

variable "enable_ops_ingress" {
  description = "Own the complete ingress config of the dedicated ops tunnel."
  type        = bool
  default     = false
}

variable "publish_ops_dns" {
  description = "Publish the public proxied CNAME only after all safety gates."
  type        = bool
  default     = false
}

variable "dedicated_tunnel_verified" {
  type    = bool
  default = false
}

variable "access_policy_verified" {
  description = "Operator-confirmed owner allowlist, deny-by-default and enforced MFA."
  type        = bool
  default     = false
}

variable "fastapi_origin_jwt_verified" {
  description = "Operator-confirmed FastAPI JWT validation and direct-origin deny tests."
  type        = bool
  default     = false
}

variable "public_site_redaction_verified" {
  description = "Site Alban public JSON/HTML/JS and cached exports confirmed clean."
  type        = bool
  default     = false
}

variable "private_origin_https_url" {
  description = "TLS-verified private vhost on TrueNAS; NOT an admin or metrics path."
  type        = string
  default     = ""
}

variable "access_application_audience" {
  description = "Cloudflare Access application AUD for ops hostname; no JWT value."
  type        = string
  default     = ""
}

variable "access_team_name" {
  description = "Cloudflare Zero Trust team name for connector JWT verification."
  type        = string
  default     = ""
}
