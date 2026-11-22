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

variable "workstation_tunnel_id" {
  description = "Workstation tunnel nabla-albandrieu (cloudflared on 172.17.0.57); its config resource owns EVERY route of that tunnel."
  type        = string
  default     = "ab5097ef-dc8c-4409-9055-99eb22aa2fbe"
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

# Written by scripts/cloudflare/capture-dns-records.py --write into
# dns-record-ids.auto.tfvars (record identifiers are not secrets).
variable "dns_tunnel_record_ids" {
  description = "Live record id of each tunnel hostname CNAME, keyed by hostname (import-first)."
  type        = map(string)
  default     = {}
}

variable "dns_retired_record_ids" {
  description = "Live record id of each retired record, keyed by \"<name>/<TYPE>\"."
  type        = map(string)
  default     = {}
}

variable "dns_retirement_phase" {
  description = "adopt: import retired records unchanged; retire: destroy them (second reviewed plan)."
  type        = string
  default     = "adopt"

  validation {
    condition     = contains(["adopt", "retire"], var.dns_retirement_phase)
    error_message = "dns_retirement_phase must be adopt or retire."
  }
}

variable "freshrss_site_service_token_id" {
  description = "Access service token of nabla-site-alban for the FreshRSS GReader API; empty until the owner creates it."
  type        = string
  default     = ""
}

# Free owns the reverse zone for 82.66.4.247; Cloudflare owns only the forward A.
# No default opt-in: avoid duplicating an existing dashboard-managed A record.
variable "home_dns_a_record_id" {
  description = "Existing home.albandrieu.com/A record ID from the Cloudflare zone inventory; set to adopt without duplicate creation."
  type        = string
  default     = ""
}

variable "home_dns_a_create_approved" {
  description = "Explicitly allow creating home.albandrieu.com/A only after Cloudflare zone API confirms this name does not already exist."
  type        = bool
  default     = false
}

variable "albanandrieu_zone_id" {
  description = "albanandrieu.com zone identifier (mail records only, mail.tofu)."
  type        = string
}

variable "mail_spf_record_ids" {
  description = "Live id of each apex SPF TXT record of mail.tofu, keyed by domain (import-first)."
  type        = map(string)
}

variable "mail_zone_ids" {
  description = "Zone id (not a secret) of each owned zone other than albandrieu.com and albanandrieu.com, keyed by domain (mail.tofu)."
  type        = map(string)
}

variable "mail_dmarc_record_ids" {
  description = "Live id of each existing _dmarc TXT record of mail.tofu, keyed by domain (import-first)."
  type        = map(string)
}

variable "fastapi_github_webhook_edge_ready" {
  description = "Explicitly enable the webhook path Access exception only after receiver and exact host/path/method/GitHub hook IP WAF acceptance."
  type        = bool
  default     = false
}

variable "fastapi_sample_tunnel_via_traefik" {
  description = "Canary public-origin cutover: false keeps 8091; true requires prior Traefik CrowdSec/LAPI/TLS/real-IP/WAF acceptance."
  type        = bool
  default     = false
}

# Honeypot staged cutover. Keep the legacy Project Honey Pot harvest script
# directly behind the tunnel until Traefik+CrowdSec/real-IP/TLS tests pass.
# The CNAME itself is managed separately through dns-policy.yaml.
variable "honeypot_tunnel_via_traefik" {
  description = "False keeps honeypot :31090; true routes login through Traefik AppSec after explicit acceptance."
  type        = bool
  default     = false
}
