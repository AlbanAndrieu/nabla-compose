# The existing Bababou project is NOT created or owned by this Terraform unit.
# Import the live WAF before planning. Never apply against an empty state.
variable "bababou_project_id" {
  type        = string
  description = "Existing Vercel project ID for nabla-site-bababou"
  default     = "prj_9eUAYmWQtHFIRKIOBYsumhU3QLU0"
}

variable "vercel_team_id" {
  type        = string
  description = "Vercel team that owns the existing project"
  default     = "team_3vukFMXCzaUZEyGAqLAGmXaf"
}

variable "enable_api_rate_limit" {
  type        = bool
  description = "Enable API rate limiting only after verifying routes, CI/ZAP and WAF events"
  default     = false
}

resource "vercel_firewall_config" "bababou" {
  project_id = var.bababou_project_id
  team_id    = var.vercel_team_id

  # Observed baseline (2026-11-21): these are LOG, not DENY.
  # Preserve current behavior at import. Promote only after false-positive review.
  managed_rulesets {
    owasp {
      gen  = { action = "log" }
      rce  = { action = "log" }
      xss  = { action = "log" }
      sqli = { action = "log" }
    }

    bot_protection {
      action = "challenge"
      active = true
    }
  }

  rules {
    rule {
      name        = "Bababou API rate limit"
      description = "Staged per-client limit for /api; require ZAP and CI allowlist validation"
      active      = var.enable_api_rate_limit
      condition_group = [{
        conditions = [{
          type  = "path"
          op    = "pre"
          value = "/api/"
        }]
      }]
      action = {
        action = "rate_limit"
        rate_limit = {
          limit  = 100
          window = 300
          keys   = ["ip"]
          algo   = "fixed_window"
          action = "deny"
        }
        action_duration = "5m"
      }
    }
  }
}
