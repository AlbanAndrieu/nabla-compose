variable "enabled" {
  description = "Enable creation of the TrueNAS Talos test resources."
  type        = bool
  default     = false
}

variable "truenas_url" {
  description = "TrueNAS HTTPS base URL."
  type        = string
  default     = ""
}

variable "truenas_api_key" {
  description = "API key used by the TrueNAS OpenTofu provider."
  type        = string
  sensitive   = true
  default     = ""
}

variable "truenas_read_only" {
  description = "Block all provider mutations. Keep true for the first plans."
  type        = bool
  default     = true
}

variable "truenas_destroy_protection" {
  description = "Block destructive provider calls during the first write tests."
  type        = bool
  default     = true
}

variable "truenas_insecure_skip_verify" {
  description = "Disable TLS certificate verification. Prefer trusting the TrueNAS CA instead."
  type        = bool
  default     = false
}

variable "truenas_pool" {
  description = "Existing TrueNAS ZFS pool used for Talos VM zvols."
  type        = string
  default     = ""
}

variable "talos_zvol_parent" {
  description = "Existing dataset path, relative to the pool, that will contain Talos VM zvols."
  type        = string
  default     = "k8s/talos-vms"
}

variable "vm_bridge" {
  description = "Existing TrueNAS bridge attached to Talos VM NICs."
  type        = string
  default     = "br0"
}

variable "talos_iso_path" {
  description = "Optional TrueNAS-local Talos ISO path. Leave empty to create VMs without a CDROM device."
  type        = string
  default     = ""
}

variable "talos_vms" {
  description = "Minimal Talos test VMs. TrueNAS VM names cannot contain hyphens or underscores."
  type = map(object({
    memory_mib    = number
    cores         = number
    disk_size_gib = number
  }))

  default = {
    taloscp01 = {
      memory_mib    = 4096
      cores         = 2
      disk_size_gib = 32
    }
    taloswk01 = {
      memory_mib    = 4096
      cores         = 2
      disk_size_gib = 32
    }
    taloswk02 = {
      memory_mib    = 4096
      cores         = 2
      disk_size_gib = 32
    }
  }
}
