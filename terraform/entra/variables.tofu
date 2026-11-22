variable "tenant_id" {
  description = "GUID of personal Nabla tenant only; NEVER employer tenant."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$", var.tenant_id))
    error_message = "An explicit tenant GUID is required."
  }
}
variable "nabla_tenant_confirmed" {
  type    = bool
  default = false
}
variable "name_prefix" {
  type    = string
  default = "nabla-iam"
}
variable "test_users" {
  description = "Existing UPNs to add to Nabla groups; the one managed test user lives in users.tofu."
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

# One-time, explicitly approved workstation bootstrap. CI keeps the two apps
# declared, but has no authorization to create, mutate or delete them.
variable "enable_ci_identity_bootstrap" {
  description = "Opt-in to GitHub OIDC plan/apply registration bootstrap in the trusted personal tenant."
  type        = bool
  default     = false
}

variable "ci_bootstrap_operator_object_id" {
  description = "Entra directory object ID of the personal operator, not an email; stable across CLI and OIDC."
  type        = string
  default     = ""
  validation {
    condition = (
      var.ci_bootstrap_operator_object_id == "" ||
      can(regex("^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$", var.ci_bootstrap_operator_object_id))
    )
    error_message = "Use the Entra user Object ID (GUID), not UPN or subscription ID."
  }
}

variable "enable_workload_pilot" {
  description = "Separate opt-in to create the pre-existing reader/denied demo workload apps."
  type        = bool
  default     = false
}
