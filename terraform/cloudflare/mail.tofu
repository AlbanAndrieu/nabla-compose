# Mail authentication of the two personal domains. Owner decision (20/11/2026):
# Google Workspace alone sends and receives for albandrieu.com and
# albanandrieu.com (not bababou.com). MX, DKIM (google._domainkey) and DMARC
# (p=reject, strict alignment) already match and stay dashboard-owned; this
# file hard-fails SPF and publishes TLS reporting. The external scan
# (scripts/security/check-public-mail-auth.py) enforces the same policy.
# MTA-STS and CAA are proposed only (README).

locals {
  mail_domains = {
    "albandrieu.com"   = { zone_id = var.zone_id, spf_ttl = 1 }
    "albanandrieu.com" = { zone_id = var.albanandrieu_zone_id, spf_ttl = 3600 }
  }
}

# Imported (imports.tofu): the plan must show only ~all becoming -all.
resource "cloudflare_dns_record" "mail_spf" {
  for_each = local.mail_domains

  zone_id = each.value.zone_id
  name    = each.key
  type    = "TXT"
  content = "\"v=spf1 include:_spf.google.com -all\""
  proxied = false
  ttl     = each.value.spf_ttl
  tags    = []

  lifecycle {
    prevent_destroy = true
  }
}

# Created: no TLS-RPT record exists. Reports go to the DMARC technical mailbox.
resource "cloudflare_dns_record" "mail_tls_rpt" {
  for_each = local.mail_domains

  zone_id = each.value.zone_id
  name    = "_smtp._tls.${each.key}"
  type    = "TXT"
  content = "\"v=TLSRPTv1; rua=mailto:technical@${each.key}\""
  proxied = false
  ttl     = 1
  tags    = []

  lifecycle {
    prevent_destroy = true
  }
}
