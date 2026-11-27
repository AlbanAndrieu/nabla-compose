# nabla-site-alban firewall (www.albanandrieu.com), adopted on 27/11/2026 at the
# live baseline read from the Vercel API: bot challenge, OWASP in log, no custom
# rule. The project and its deployments stay in nabla-site-alban. A rate-limit
# rule is a later, reviewed change (one rule per project on Hobby).
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

  lifecycle {
    prevent_destroy = true
  }
}
