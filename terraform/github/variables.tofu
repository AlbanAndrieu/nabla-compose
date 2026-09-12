variable "github_owner" {
  description = "GitHub user or organization that owns the repositories."
  type        = string
  default     = "AlbanAndrieu"
}

variable "github_governance_enabled" {
  description = "Master safety switch. When false, this module creates or changes no GitHub resources."
  type        = bool
  default     = false
}

variable "github_inventory_enabled" {
  description = "Enable read-only discovery of non-archived, non-fork repositories owned by github_owner."
  type        = bool
  default     = false
}

variable "manage_rulesets" {
  description = "Allow this module to manage repository rulesets when github_governance_enabled is also true."
  type        = bool
  default     = false
}

variable "manage_actions_permissions" {
  description = "Allow this module to manage repository GitHub Actions policy when github_governance_enabled is also true."
  type        = bool
  default     = false
}

variable "manage_workflow_permissions" {
  description = "Allow this module to manage default GITHUB_TOKEN permissions when github_governance_enabled is also true."
  type        = bool
  default     = false
}

variable "ruleset_enforcement" {
  description = "Ruleset enforcement mode. Keep disabled during inventory/pilot preparation."
  type        = string
  default     = "disabled"

  validation {
    condition     = contains(["disabled", "active"], var.ruleset_enforcement)
    error_message = "ruleset_enforcement must be disabled or active for personal repositories."
  }
}

variable "release_app_id" {
  description = "Optional GitHub App ID allowed to bypass the default-branch ruleset for controlled semantic-release writes."
  type        = number
  default     = null
  nullable    = true
}

variable "repositories" {
  description = "Explicit repository policy allow-list. Repositories are never auto-enrolled from inventory."
  type = map(object({
    required_checks                   = optional(set(string), [])
    required_approving_review_count   = optional(number, 0)
    required_review_thread_resolution = optional(bool, true)
    allowed_merge_methods             = optional(set(string), ["merge", "squash", "rebase"])
    actions_enabled                   = optional(bool, true)
    sha_pinning_required              = optional(bool, true)
    default_workflow_permissions      = optional(string, "read")
    can_approve_pull_request_reviews  = optional(bool, false)
  }))
  default = {}

  validation {
    condition = alltrue([
      for policy in values(var.repositories) :
      policy.required_approving_review_count >= 0 &&
      policy.required_approving_review_count <= 6
    ])
    error_message = "required_approving_review_count must be between 0 and 6."
  }

  validation {
    condition = alltrue([
      for policy in values(var.repositories) :
      length(policy.allowed_merge_methods) > 0 &&
      length(setsubtract(policy.allowed_merge_methods, toset(["merge", "squash", "rebase"]))) == 0
    ])
    error_message = "allowed_merge_methods must contain only merge, squash, or rebase and cannot be empty."
  }

  validation {
    condition = alltrue([
      for policy in values(var.repositories) :
      contains(["read", "write"], policy.default_workflow_permissions)
    ])
    error_message = "default_workflow_permissions must be read or write."
  }
}
