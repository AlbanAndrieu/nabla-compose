include "root" { path = find_in_parent_folders("root.hcl") }

terraform { source = find_in_parent_folders("terraform/github") }

inputs = {
  github_owner = "AlbanAndrieu"

  # Master switch on for repository settings only. The other switches MUST
  # remain false until an explicit, reviewed activation change is approved.
  github_governance_enabled   = true
  github_inventory_enabled    = false
  manage_rulesets             = false
  manage_actions_permissions  = false
  manage_workflow_permissions = false
  manage_repository_settings  = true

  # Imported on the next apply; only delete_branch_on_merge is managed.
  # Named repositories plus the 10 others with the most default-branch commits over 90 days (12/11/2026).
  managed_repositories = [
    "ansible-cpp",
    "ansible-jenkins-slave-docker",
    "ansible-nabla",
    "ansible-shell",
    "ansible-workstation",
    "fastapi-sample",
    "nabla",
    "nabla-compose",
    "nabla-cpp",
    "nabla-hooks",
    "nabla-memo",
    "nabla-openclaw",
    "nabla-projects-interview-visma",
    "nabla-servers-bower-sample",
    "nabla-site-alban",
    "nabla-site-bababou",
    "nabla-yubikey",
  ]

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
