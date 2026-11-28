# Bot Fight Mode of albandrieu.com, off by owner decision (27/11/2026). On the
# Free plan no WAF rule can skip it, and it answered every call of the site
# support chat from Vercel (AWS ASN 16509) with a 403 managed challenge before
# Cloudflare Access could check the service token. Access still guards the
# private hosts; the other bot settings stay as imported.
resource "cloudflare_bot_management" "albandrieu" {
  zone_id    = var.zone_id
  fight_mode = false
  # Provider 5.28.1 plans it false when unset, turning the managed robots.txt off.
  is_robots_txt_managed = true

  lifecycle {
    prevent_destroy = true
  }
}
