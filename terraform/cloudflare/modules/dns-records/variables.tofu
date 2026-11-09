variable "zone_id" {
  description = "Cloudflare zone identifier."
  type        = string
}

variable "tunnel_target" {
  description = "CNAME target of tunnel routes: <tunnel id>.cfargotunnel.com."
  type        = string
}

variable "tunnel_hostnames" {
  description = "Public hostnames routed by the tunnel; each gets a proxied CNAME."
  type        = set(string)
}

variable "tunnel_record_ids" {
  description = "Live record id of each tunnel hostname (import-first)."
  type        = map(string)
  default     = {}
}

variable "new_tunnel_hostnames" {
  description = "Tunnel hostnames allowed to be created because no record exists yet."
  type        = list(string)
  default     = []
}

variable "retired_hostnames" {
  description = "Hostnames that must disappear from public DNS."
  type        = set(string)
  default     = []
}

variable "retired_record_ids" {
  description = "Live record id of each retired record, keyed by \"<name>/<TYPE>\"."
  type        = map(string)
  default     = {}
}

variable "retirement_phase" {
  description = "adopt: keep retired records in configuration for import; retire: drop them so the plan destroys them."
  type        = string
  default     = "adopt"

  validation {
    condition     = contains(["adopt", "retire"], var.retirement_phase)
    error_message = "retirement_phase must be adopt or retire."
  }
}
