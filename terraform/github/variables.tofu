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

variable "manage_repository_settings" {
  description = "Allow this module to import managed_repositories and enforce delete_branch_on_merge when github_governance_enabled is also true."
  type        = bool
  default     = false
}

variable "managed_repositories" {
  description = "Repositories imported as github_repository. Only delete_branch_on_merge is managed; every other setting stays as configured on GitHub."
  type        = set(string)
  default     = []
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

variable "ruleset_import_ids" {
  description = "Existing \"Protect master\" ruleset IDs, by repository, adopted by import on the next apply."
  type        = map(number)
  default     = {}
}

variable "github_app_id" {
  description = "GitHub App ID used for provider authentication when github_app_installation_id is set."
  type        = number
  default     = null
  nullable    = true
}

variable "github_app_installation_id" {
  description = "Installation ID of github_app_id; null keeps the GITHUB_TOKEN authentication."
  type        = number
  default     = null
  nullable    = true
}

variable "github_app_pem" {
  description = "PEM content of github_app_id, from TF_VAR_github_app_pem only (provider configuration is not stored in the state)."
  type        = string
  default     = null
  nullable    = true
  sensitive   = true
}

variable "release_app_client_id" {
  description = "Client ID of the release GitHub App, published as the RELEASE_APP_CLIENT_ID Actions variable."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.release_app_client_id == null || can(regex("^Iv[0-9A-Za-z]{18}$", var.release_app_client_id))
    error_message = "release_app_client_id must be a full GitHub App client ID (Iv + 18 characters)."
  }
}

variable "release_app_client_id_repositories" {
  description = "Repositories whose release workflow mints a release App token."
  type        = set(string)
  default     = []
}

variable "repositories" {
  description = "Explicit repository policy allow-list. Repositories are never auto-enrolled from inventory."
  type = map(object({
    # Check context => GitHub App ID that reports it (46505 GitGuardian, 15368 GitHub Actions).
    required_checks                   = optional(map(number), { "GitGuardian Security Checks" = 46505 })
    required_approving_review_count   = optional(number, 0)
    required_review_thread_resolution = optional(bool, true)
    allowed_merge_methods             = optional(set(string), ["squash"])
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
