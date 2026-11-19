include "root" { path = find_in_parent_folders("root.hcl") }

terraform { source = find_in_parent_folders("terraform/github") }

inputs = {
  github_owner = "AlbanAndrieu"

  # Repository settings and default-branch rulesets are managed. Actions and
  # workflow-token switches MUST remain false until a reviewed activation.
  github_governance_enabled   = true
  github_inventory_enabled    = false
  manage_rulesets             = true
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

  # Personal-account rulesets cannot use evaluate mode. Active since 19/11/2026
  # on every public, non-fork repository (private ones need GitHub Pro).
  ruleset_enforcement = "active"

  # Dedicated release App `fastapi-sample-release`: its only bypass. It must be
  # installed on every repository below, or the apply fails with a 422.
  release_app_id = 4676280

  # "Protect master" rulesets created through the API on 19/11/2026, adopted by import.
  # The separate "Code quality" ruleset stays outside OpenTofu: provider 6.13 has no
  # code_quality rule (infrastructure/github/README.md).
  ruleset_import_ids = {
    "AlbanAndrieu"                         = 27676847
    "ansible-administration"               = 27676850
    "ansible-cmake"                        = 27676855
    "ansible-common"                       = 27676861
    "ansible-conky"                        = 27676865
    "ansible-cpp"                          = 27676867
    "ansible-css"                          = 27676872
    "ansible-dns"                          = 27676876
    "ansible-dropbox"                      = 27676885
    "ansible-eclipse"                      = 27676894
    "ansible-gcc"                          = 27676897
    "ansible-grive"                        = 27676901
    "ansible-hostname"                     = 27676908
    "ansible-java-certificate"             = 27676912
    "ansible-jenkins-slave-docker"         = 27676915
    "ansible-logstash-settings"            = 27676925
    "ansible-nabla"                        = 27676931
    "ansible-owasp-wte"                    = 27676938
    "ansible-role-ruby"                    = 27676947
    "ansible-selenium"                     = 27676959
    "ansible-shell"                        = 27676963
    "ansible-synergy"                      = 27676973
    "ansible-tomcat"                       = 27676976
    "ansible-web"                          = 27676983
    "ansible-windows"                      = 27676989
    "ansible-workstation"                  = 27675386
    "ansible-xvbf"                         = 27676994
    "ansible-zap"                          = 27676999
    "dotfiles"                             = 27675384
    "fastapi-sample"                       = 21167545
    "nabla-andromda"                       = 27677009
    "nabla-build-tools"                    = 27677012
    "nabla-compose"                        = 27675208
    "nabla-cpp"                            = 27677032
    "nabla-databases"                      = 27677060
    "nabla-hooks"                          = 27677066
    "nabla-jenkins-scm-sync-configuration" = 27677075
    "nabla-maven"                          = 27677080
    "nabla-openclaw"                       = 27675387
    "nabla-projects"                       = 27677102
    "nabla-projects-interview-fronter"     = 27677089
    "nabla-projects-interview-visma"       = 27677097
    "nabla-servers"                        = 27677112
    "nabla-servers-bower-sample"           = 27677106
    "nabla-site-alban"                     = 27355874
    "nabla-site-apache"                    = 27677127
    "nabla-site-bababou"                   = 27676476
    "nabla-site-react"                     = 27677144
    "nabla-uml"                            = 27677148
    "nabla-yubikey"                        = 27675388
    "thiga-ai"                             = 27676841
    "truenas-apps"                         = 27677158
  }

  # Explicit allow-list: discovery never auto-enrols repositories. The default
  # policy requires GitGuardian and squash merges only.
  repositories = {
    "ansible-jenkins-slave-docker" = {
      required_checks = {
        "GitGuardian Security Checks" = 46505
        "Agent preflight"             = 15368
        "Build Docker"                = 15368
        "Mega Linter"                 = 15368
      }

      # Solo-owner baseline: PR required but no external approval required.
      required_approving_review_count   = 0
      required_review_thread_resolution = true

      # Prepared defaults for later staged activation.
      sha_pinning_required             = true
      default_workflow_permissions     = "read"
      can_approve_pull_request_reviews = false
    }
    "AlbanAndrieu"              = {}
    "ansible-administration"    = {}
    "ansible-cmake"             = {}
    "ansible-common"            = {}
    "ansible-conky"             = {}
    "ansible-cpp"               = {}
    "ansible-css"               = {}
    "ansible-dns"               = {}
    "ansible-dropbox"           = {}
    "ansible-eclipse"           = {}
    "ansible-gcc"               = {}
    "ansible-grive"             = {}
    "ansible-hostname"          = {}
    "ansible-java-certificate"  = {}
    "ansible-logstash-settings" = {}
    "ansible-nabla"             = {}
    "ansible-owasp-wte"         = {}
    "ansible-role-ruby"         = {}
    "ansible-selenium"          = {}
    "ansible-shell"             = {}
    "ansible-synergy"           = {}
    "ansible-tomcat"            = {}
    "ansible-web"               = {}
    "ansible-windows"           = {}
    "ansible-workstation"       = {}
    "ansible-xvbf"              = {}
    "ansible-zap"               = {}
    # Fork without GitGuardian reports: no required check.
    "dotfiles" = { required_checks = {} }
    "fastapi-sample" = {
      required_checks = {
        "GitGuardian Security Checks"                           = 46505
        "Test dependencies and optionally build Python package" = 15368
      }
    }
    "nabla-andromda"                       = {}
    "nabla-build-tools"                    = {}
    "nabla-compose"                        = {}
    "nabla-cpp"                            = {}
    "nabla-databases"                      = {}
    "nabla-hooks"                          = {}
    "nabla-jenkins-scm-sync-configuration" = {}
    "nabla-maven"                          = {}
    "nabla-openclaw"                       = {}
    "nabla-projects"                       = {}
    "nabla-projects-interview-fronter"     = {}
    "nabla-projects-interview-visma"       = {}
    "nabla-servers"                        = {}
    "nabla-servers-bower-sample"           = {}
    "nabla-site-alban"                     = {}
    "nabla-site-apache"                    = {}
    "nabla-site-bababou"                   = {}
    "nabla-site-react"                     = {}
    "nabla-uml"                            = {}
    "nabla-yubikey"                        = {}
    "thiga-ai"                             = {}
    "truenas-apps"                         = {}
  }
}
