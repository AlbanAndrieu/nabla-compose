provider "github" {
  owner = var.github_owner
}

data "github_repositories" "owned" {
  count = var.github_inventory_enabled ? 1 : 0

  query           = "user:${var.github_owner} archived:false fork:false"
  include_repo_id = true
}

resource "github_repository_ruleset" "default_branch" {
  for_each = var.github_governance_enabled && var.manage_rulesets ? var.repositories : {}

  repository  = each.key
  name        = "nabla-default-branch"
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
    deletion         = true
    non_fast_forward = true

    pull_request {
      allowed_merge_methods               = sort(tolist(each.value.allowed_merge_methods))
      dismiss_stale_reviews_on_push       = false
      require_code_owner_review           = false
      require_last_push_approval           = false
      required_approving_review_count     = each.value.required_approving_review_count
      required_review_thread_resolution   = each.value.required_review_thread_resolution
    }

    dynamic "required_status_checks" {
      for_each = length(each.value.required_checks) == 0 ? [] : [each.value.required_checks]

      content {
        # Intentionally mirrors "Require branches to be up to date before merging" = OFF.
        strict_required_status_checks_policy = false

        dynamic "required_check" {
          for_each = required_status_checks.value

          content {
            context = required_check.value
          }
        }
      }
    }
  }
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
