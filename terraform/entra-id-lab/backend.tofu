# HCP Terraform Free is state-only. Workspace MUST use LOCAL execution mode.
# The runner and workstation supply organization/workspaces via -backend-config.
terraform {
  backend "remote" {}
}
