variable "account_id" {
  description = "Cloudflare account identifier (not a secret)."
  type        = string
  default     = "bdfe00eeee5845782ab91adfbff71ee1"
}

variable "tunnel_id" {
  description = "Shared dashboard-managed homelab tunnel; its config resource owns EVERY public hostname route."
  type        = string
  default     = "1d98bede-6fa0-42a8-971c-cd390d74d7f6"
}

# The identifiers below are discovered read-only by
# scripts/cloudflare/capture-homelab-tofu.sh into import-ids.auto.tfvars.
variable "zone_id" {
  description = "albandrieu.com zone identifier."
  type        = string
}

variable "fastapi_sample_dns_record_id" {
  description = "Proxied CNAME of the FastAPI Sample public hostname."
  type        = string
}

variable "fastapi_sample_access_application_id" {
  description = "Host-wide Cloudflare Access self-hosted application protecting FastAPI Sample."
  type        = string
}

variable "fastapi_sample_api_access_application_id" {
  description = "Path-scoped Access application for FastAPI Sample /api (no monitor service token)."
  type        = string
}
