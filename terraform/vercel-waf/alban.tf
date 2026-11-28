# nabla-site-alban firewall (www.albanandrieu.com), adopted on 27/11/2026 at the
# live baseline read from the Vercel API: bot challenge, OWASP in log, no custom
# rule. The project and its deployments stay in nabla-site-alban.
# One Hobby-compatible per-IP rule is now scoped to /api/support-chat only.
variable "alban_project_id" {
  type        = string
  description = "Existing Vercel project ID for nabla-site-alban"
  default     = "prj_x6leAdsVXdHRcoG1zsSiy5pngEYa"
}

# Adopt the existing firewall into the Garage state, never create a second one.
import {
  to = vercel_firewall_config.alban
  id = "team_3vukFMXCzaUZEyGAqLAGmXaf/prj_x6leAdsVXdHRcoG1zsSiy5pngEYa"
}

variable "alban_support_kill_switch" {
  type        = bool
  default     = false
  description = "Emergency WAF kill switch: deny all production support-chat requests at the edge"
}

resource "vercel_firewall_config" "alban" {
  project_id = var.alban_project_id
  team_id    = var.vercel_team_id
  enabled    = true

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

  # ONE rule on Hobby, matching only the real paid assistant endpoint.
  # Switch action to deny for immediate shutdown without consuming model tokens.
  rules {
    rule {
      name        = "Site Alban support chatbot budget guard"
      description = "Per-IP 6 questions / 5 minutes, or immediate deny when the emergency switch is set"
      active      = true
      condition_group = [
        {
          conditions = [
            { type = "host", op = "eq", value = "www.albanandrieu.com" },
            { type = "path", op = "eq", value = "/api/support-chat" },
          ]
        },
        {
          conditions = [
            { type = "host", op = "eq", value = "albanandrieu.com" },
            { type = "path", op = "eq", value = "/api/support-chat" },
          ]
        },
      ]
      action = {
        action = var.alban_support_kill_switch ? "deny" : "rate_limit"
        rate_limit = var.alban_support_kill_switch ? null : {
          limit  = 6
          window = 300
          keys   = ["ip"]
          algo   = "fixed_window"
          action = "deny"
        }
      }
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}
