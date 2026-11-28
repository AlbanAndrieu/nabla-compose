# Bababou project and its deployments are managed outside this unit.
# This resource must be IMPORTED into the shared Garage state before any apply.
variable "bababou_project_id" {
  type        = string
  description = "Existing Vercel project ID for nabla-site-bababou"
  default     = "prj_9eUAYmWQtHFIRKIOBYsumhU3QLU0"
}

variable "vercel_team_id" {
  type        = string
  description = "Vercel team that owns the existing Bababou project"
  default     = "team_3vukFMXCzaUZEyGAqLAGmXaf"
}

# OWASP Core managed ruleset requires Enterprise. On Hobby/Pro, keep the
# previously observed LOG baseline so rate limiting can be reviewed separately.
variable "enable_owasp_blocking" {
  type        = bool
  description = "Enable managed SQLi/XSS/RCE deny only after confirming Vercel Enterprise entitlement"
  default     = false
}

locals {
  owasp_attack_action = var.enable_owasp_blocking ? "deny" : "log"
}

resource "vercel_firewall_config" "bababou" {
  project_id = var.bababou_project_id
  team_id    = var.vercel_team_id
  enabled    = true

  # Observed on 2026-11-21: gen was LOG and the three attack groups were LOG.
  # Enterprise opt-in: BLOCK SQLi/XSS/RCE; otherwise keep existing LOG baseline.
  # while checking false positives. Preserve existing bot challenges.
  managed_rulesets {
    owasp {
      gen  = { action = "log", active = true }
      sqli = { action = local.owasp_attack_action, active = true }
      xss  = { action = local.owasp_attack_action, active = true }
      rce  = { action = local.owasp_attack_action, active = true }
    }

    bot_protection {
      action = "challenge"
      active = true
    }
  }

  # Exactly ONE rate-limiting rule (Vercel Hobby project limit).
  # Conditions within a group are AND; separate groups are OR.
  # Scope to verified public custom domains, not the Vercel preview aliases:
  # ZAP CI is configured to run at <= 1 req/s and uses the preview aliases.
  rules {
    rule {
      name        = "Bababou public traffic rate limit"
      description = "Production custom domains: per-IP 300 requests/minute; fixed-window deny"
      active      = true
      condition_group = [
        {
          conditions = [{
            type  = "host"
            op    = "eq"
            value = "www.bababou.com"
          }]
        },
        {
          conditions = [{
            type  = "host"
            op    = "eq"
            value = "bababou.com"
          }]
        },
        {
          conditions = [{
            type  = "host"
            op    = "eq"
            value = "bababou.albandrieu.com"
          }]
        },
      ]

      action = {
        action = "rate_limit"
        rate_limit = {
          limit  = 300
          window = 60
          keys   = ["ip"]
          algo   = "fixed_window"
          action = "deny"
        }
        # Persistent action_duration is Pro/Enterprise only; omit for Hobby.
      }
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}
