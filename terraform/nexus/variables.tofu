variable "nexus_url" {
  type = string
}

variable "nexus_username" {
  type = string
}

variable "nexus_password" {
  type      = string
  sensitive = true
}

variable "enabled_formats" {
  description = "Repository formats this root manages. Widen one format per reviewed plan/apply (N1 apt, N2 npm, N3 pypi, N4 docker)."
  type        = set(string)
  default     = ["apt"]

  validation {
    condition     = length(setsubtract(var.enabled_formats, ["apt", "docker", "huggingface", "npm", "pypi", "terraform"])) == 0
    error_message = "enabled_formats accepts only apt, docker, huggingface, npm, pypi and terraform."
  }
}

variable "manage_realms" {
  description = "Manage the active security realms. The resource replaces the whole live list: keep false until system.tofu matches the live list."
  type        = bool
  default     = false
}

variable "manage_rbac" {
  description = "Manage the local roles and users; user passwords come from nexus_user_passwords."
  type        = bool
  default     = false
}

variable "nexus_user_passwords" {
  description = "Local user passwords keyed by user_id (home-ops, albandrieu), supplied out of Git from Vaultwarden (TF_VAR_nexus_user_passwords)."
  type        = map(string)
  sensitive   = true
  default     = {}
}
