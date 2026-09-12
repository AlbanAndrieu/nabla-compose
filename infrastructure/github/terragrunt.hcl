include "root" { path = find_in_parent_folders("root.hcl") }

terraform { source = find_in_parent_folders("terraform/github") }

inputs = {
  github_owner = "AlbanAndrieu"

  # Preparation only. These switches MUST remain false until an explicit,
  # reviewed activation change is approved.
  github_governance_enabled   = false
  github_inventory_enabled    = false
  manage_rulesets             = false
  manage_actions_permissions  = false
  manage_workflow_permissions = false

  # Personal-account rulesets cannot use evaluate mode. Start with a disabled
  # ruleset during the pilot, then activate only after the plan is reviewed.
  ruleset_enforcement = "disabled"

  # Populate only after a dedicated release GitHub App exists and its App ID is
  # verified. Never use a broad user/admin bypass for semantic-release.
  release_app_id = null

  # Explicit allow-list: discovery never auto-enrols repositories.
  repositories = {
    "ansible-jenkins-slave-docker" = {
      required_checks = [
        "Agent preflight",
        "Build Docker",
        "Mega Linter",
      ]

      # Solo-owner baseline: PR required but no external approval required.
      required_approving_review_count   = 0
      required_review_thread_resolution = true

      # Prepared defaults for later staged activation.
      sha_pinning_required             = true
      default_workflow_permissions     = "read"
      can_approve_pull_request_reviews = false
    }
  }
}
