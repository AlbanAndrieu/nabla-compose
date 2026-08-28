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

variable "truenas_username" {
  description = "TrueNAS service-account username that owns the API key. Required by the modern auth flow and recommended on TrueNAS 26+."
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

  validation {
    condition     = length(trimspace(var.talos_zvol_parent)) > 0 && !startswith(var.talos_zvol_parent, "/") && !endswith(var.talos_zvol_parent, "/")
    error_message = "talos_zvol_parent must be a non-empty pool-relative dataset path without leading or trailing slashes."
  }
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

  validation {
    condition     = var.talos_iso_path == "" || startswith(var.talos_iso_path, "/")
    error_message = "talos_iso_path must be empty or an absolute TrueNAS-local path."
  }
}

variable "talos_vms" {
  description = "Minimal Talos test VMs with deterministic locally administered MAC addresses for DHCP reservations."
  type = map(object({
    memory_mib    = number
    cores         = number
    disk_size_gib = number
    mac           = string
  }))

  default = {
    taloscp01 = {
      memory_mib    = 4096
      cores         = 2
      disk_size_gib = 32
      mac           = "02:00:00:00:10:01"
    }
    taloswk01 = {
      memory_mib    = 4096
      cores         = 2
      disk_size_gib = 32
      mac           = "02:00:00:00:20:01"
    }
    taloswk02 = {
      memory_mib    = 4096
      cores         = 2
      disk_size_gib = 32
      mac           = "02:00:00:00:20:02"
    }
  }

  validation {
    condition     = length(var.talos_vms) > 0
    error_message = "talos_vms must declare at least one VM."
  }

  validation {
    condition     = alltrue([for name in keys(var.talos_vms) : can(regex("^[A-Za-z0-9]+$", name))])
    error_message = "Talos VM names must contain only letters and digits; hyphens and underscores are not allowed by the current TrueNAS VM naming constraint."
  }

  validation {
    condition = alltrue([
      for vm in values(var.talos_vms) :
      vm.memory_mib >= 2048 && vm.cores >= 1 && vm.disk_size_gib >= 16
    ])
    error_message = "Each Talos VM must have at least 2048 MiB RAM, 1 CPU core, and a 16 GiB disk."
  }

  validation {
    condition = alltrue([
      for vm in values(var.talos_vms) :
      can(regex("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", vm.mac)) && startswith(lower(vm.mac), "02:")
    ])
    error_message = "Each Talos VM MAC must use colon notation and the locally administered unicast 02: prefix."
  }

  validation {
    condition     = length(distinct([for vm in values(var.talos_vms) : lower(vm.mac)])) == length(var.talos_vms)
    error_message = "Talos VM MAC addresses must be unique."
  }
}
