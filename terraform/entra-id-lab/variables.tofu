variable "tenant_id" {
  description = "GUID of personal lab tenant only; NEVER employer tenant."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$", var.tenant_id))
    error_message = "An explicit tenant GUID is required."
  }
}
variable "lab_tenant_confirmed" {
  type    = bool
  default = false
}
variable "name_prefix" {
  type    = string
  default = "nabla-iam-lab"
}
variable "test_users" {
  description = "Existing UPNs to add to lab groups; the one managed test user lives in users.tofu."
  type = map(object({
    upn   = string
    group = string
  }))
  default = {}
  validation {
    condition     = alltrue([for u in values(var.test_users) : contains(["readers", "operators"], u.group)])
    error_message = "group must be readers or operators."
  }
}

variable "enable_group_management" {
  description = "OFF in CI: avoid tenant-wide Graph group write permissions."
  type        = bool
  default     = false
}
variable "ci_use_oidc" {
  type    = bool
  default = false
}
variable "ci_graph_client_id" {
  description = "CI Microsoft Graph application ID, separate from state storage identity."
  type        = string
  default     = ""
}

variable "enable_user_management" {
  description = "Workstation-only test user (users.tofu); OFF in CI."
  type        = bool
  default     = false
}
variable "test_user_initial_password" {
  description = "One-time password from Vaultwarden (TF_VAR_test_user_initial_password), replaced at first sign-in."
  type        = string
  sensitive   = true
  default     = null
}
