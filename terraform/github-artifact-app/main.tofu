terraform {
  required_version = ">= 1.8.0"

  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.13"
    }
  }
}

provider "github" {
  owner = "AlbanAndrieu"
}

variable "installation_id" {
  description = "Verified installation ID of nabla-github-app (not App ID). Empty disables the initial adoption."
  type        = string
  default     = ""

  validation {
    condition     = var.installation_id == "" || can(regex("^[1-9][0-9]*$", var.installation_id))
    error_message = "Use the verified positive installation ID, or empty for unconfigured."
  }
}

locals {
  selected_repositories = toset([
    "fastapi-sample",
    "nabla-compose",
    "nabla-site-alban",
    "nabla-site-bababou",
  ])
  installations = var.installation_id == "" ? toset([]) : toset([var.installation_id])
}

# Manifest registration and initial selected-repository consent are prerequisites.
# Import existing installation, do not create or register a GitHub App here.
import {
  for_each = local.installations
  to       = github_app_installation_repositories.artifact_reader[each.key]
  id       = each.key
}

resource "github_app_installation_repositories" "artifact_reader" {
  for_each = local.installations

  installation_id       = each.key
  selected_repositories = local.selected_repositories

  lifecycle {
    prevent_destroy = true
  }
}
