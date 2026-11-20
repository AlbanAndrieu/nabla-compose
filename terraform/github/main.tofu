provider "github" {
  owner = var.github_owner

  # GitHub App identity when TF_VAR_github_app_pem is exported for the run,
  # otherwise GITHUB_TOKEN. The PEM never comes from Git or the state.
  dynamic "app_auth" {
    for_each = var.github_app_installation_id == null || nonsensitive(var.github_app_pem == null) ? [] : [var.github_app_installation_id]

    content {
      id              = var.github_app_id
      installation_id = app_auth.value
      pem_file        = var.github_app_pem
    }
  }
}

data "github_repositories" "owned" {
  count = var.github_inventory_enabled ? 1 : 0

  query           = "user:${var.github_owner} archived:false fork:false"
  include_repo_id = true
}

locals {
  managed_repositories = var.github_governance_enabled && var.manage_repository_settings ? var.managed_repositories : toset([])
}

import {
  for_each = local.managed_repositories

  to = github_repository.managed[each.key]
  id = each.key
}

resource "github_repository" "managed" {
  for_each = local.managed_repositories

  name                   = each.key
  delete_branch_on_merge = true
  # Dropping a repository from the set must archive it, never delete it.
  archive_on_destroy = true

  lifecycle {
    # Unmanage with `state rm` before dropping the name (infrastructure/github/README.md).
    prevent_destroy = true
    # Only delete_branch_on_merge is owned here: the provider defaults of these would rewrite GitHub.
    ignore_changes = [
      allow_auto_merge,
      allow_forking,
      allow_merge_commit,
      allow_rebase_merge,
      allow_squash_merge,
      allow_update_branch,
      archived,
      auto_init,
      description,
      gitignore_template,
      has_discussions,
      has_downloads,
      has_issues,
      has_projects,
      has_wiki,
      homepage_url,
      is_template,
      license_template,
      merge_commit_message,
      merge_commit_title,
      pages,
      security_and_analysis,
      squash_merge_commit_message,
      squash_merge_commit_title,
      template,
      topics,
      visibility,
      vulnerability_alerts,
      web_commit_signoff_required,
    ]
  }
}

# Adopt rulesets created through the API before this module managed them.
import {
  for_each = var.github_governance_enabled && var.manage_rulesets ? var.ruleset_import_ids : {}

  to = github_repository_ruleset.default_branch[each.key]
  id = "${each.key}:${each.value}"
}

resource "github_repository_ruleset" "default_branch" {
  for_each = var.github_governance_enabled && var.manage_rulesets ? var.repositories : {}

  repository  = each.key
  name        = "Protect master"
  target      = "branch"
  enforcement = var.ruleset_enforcement

  conditions {
    ref_name {
      include = ["~DEFAULT_BRANCH"]
      exclude = []
    }
  }

  dynamic "bypass_actors" {
    for_each = var.release_app_id == null ? [] : [var.release_app_id]

    content {
      actor_id    = bypass_actors.value
      actor_type  = "Integration"
      bypass_mode = "always"
    }
  }

  rules {
    deletion                = true
    non_fast_forward        = true
    required_linear_history = true

    pull_request {
      allowed_merge_methods             = sort(tolist(each.value.allowed_merge_methods))
      dismiss_stale_reviews_on_push     = false
      require_code_owner_review         = false
      require_last_push_approval        = false
      required_approving_review_count   = each.value.required_approving_review_count
      required_review_thread_resolution = each.value.required_review_thread_resolution
    }

    dynamic "required_status_checks" {
      for_each = length(each.value.required_checks) == 0 ? [] : [each.value.required_checks]

      content {
        strict_required_status_checks_policy = each.value.strict_required_status_checks
        do_not_enforce_on_create             = true

        dynamic "required_check" {
          for_each = required_status_checks.value

          content {
            context        = required_check.key
            integration_id = required_check.value
          }
        }
      }
    }
  }
}

# Non-secret client ID read by create-github-app-token in release workflows.
# The private key stays a manually set Actions secret: never in the state.
import {
  for_each = var.github_governance_enabled ? var.release_app_client_id_repositories : toset([])

  to = github_actions_variable.release_app_client_id[each.key]
  id = "${each.key}:RELEASE_APP_CLIENT_ID"
}

resource "github_actions_variable" "release_app_client_id" {
  for_each = var.github_governance_enabled && var.release_app_client_id != null ? var.release_app_client_id_repositories : toset([])

  repository    = each.key
  variable_name = "RELEASE_APP_CLIENT_ID"
  value         = var.release_app_client_id
}

resource "github_actions_repository_permissions" "policy" {
  for_each = var.github_governance_enabled && var.manage_actions_permissions ? var.repositories : {}

  repository           = each.key
  enabled              = each.value.actions_enabled
  allowed_actions      = "all"
  sha_pinning_required = each.value.sha_pinning_required
}

resource "github_workflow_repository_permissions" "policy" {
  for_each = var.github_governance_enabled && var.manage_workflow_permissions ? var.repositories : {}

  repository                       = each.key
  default_workflow_permissions     = each.value.default_workflow_permissions
  can_approve_pull_request_reviews = each.value.can_approve_pull_request_reviews
}
