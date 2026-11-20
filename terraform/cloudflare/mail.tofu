# Mail authentication of the two personal domains. Owner decision (20/11/2026):
# Google Workspace alone sends and receives for albandrieu.com and
# albanandrieu.com (not bababou.com). MX, DKIM (google._domainkey) and DMARC
# (p=reject, strict alignment) already match and stay dashboard-owned; this
# file hard-fails SPF, publishes TLS reporting and MTA-STS in testing mode
# (owner decision, 20/11/2026), its policy served by a Cloudflare Worker, not
# the homelab. The external scan (scripts/security/check-public-mail-auth.py)
# enforces the same policy. CAA is proposed only (README).

locals {
  # mta_sts_mx lists exactly the published MX of each apex; the scan compares
  # the served policy with them.
  mail_domains = {
    "albandrieu.com" = {
      zone_id    = var.zone_id
      spf_ttl    = 1
      mta_sts_mx = ["aspmx.l.google.com", "*.aspmx.l.google.com", "smtp.google.com"]
    }
    "albanandrieu.com" = {
      zone_id    = var.albanandrieu_zone_id
      spf_ttl    = 3600
      mta_sts_mx = ["aspmx.l.google.com", "*.aspmx.l.google.com"]
    }
  }
  # Owner decision (20/11/2026): DMARC and TLS reports of every owned domain go
  # to one mailbox. RFC 7489 7.1: albandrieu.com authorizes each other domain
  # of config/security/public-mail-domains.json to send it DMARC reports.
  report_mailbox = "openclaw@albandrieu.com"
  dmarc_reported_domains = toset([
    "albanandrieu.com", "bababou.com", "bababou.net", "dr-alban.com", "eokoo.net",
    "eokou.com", "heoko.com", "heoko.net", "heoko.org", "heokoo.com", "heokoo.net",
    "heokoo.org", "heokou.com", "heokou.net", "heokou.org", "papapou.com", "papapou.net",
    "papapou.org", "papoyou.net",
  ])
  # RFC 8461: a new id with every policy change. enforce comes after weeks of
  # clean TLS-RPT reports (docs/roadmap.md).
  mta_sts_id = "20261120000000"
  mta_sts_policies = {
    for domain, mail in local.mail_domains : "mta-sts.${domain}" => join("\r\n", concat(
      ["version: STSv1", "mode: testing"],
      [for mx in mail.mta_sts_mx : "mx: ${mx}"],
      ["max_age: 86400", ""],
    ))
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

# Created: no TLS-RPT record exists. Reports go to the shared report mailbox.
resource "cloudflare_dns_record" "mail_tls_rpt" {
  for_each = local.mail_domains

  zone_id = each.value.zone_id
  name    = "_smtp._tls.${each.key}"
  type    = "TXT"
  content = "\"v=TLSRPTv1; rua=mailto:${local.report_mailbox}\""
  proxied = false
  ttl     = 1
  tags    = []

  lifecycle {
    prevent_destroy = true
  }
}

# Created: the policy host. No route, origin or binding; one script serves the
# two custom domains (Cloudflare creates their DNS record and certificate).
resource "cloudflare_workers_script" "mta_sts" {
  account_id         = var.account_id
  script_name        = "mta-sts"
  main_module        = "worker.js"
  compatibility_date = "2026-11-01"
  content            = templatefile("${path.module}/mta-sts-worker.js.tftpl", { policies = jsonencode(local.mta_sts_policies) })

  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_workers_custom_domain" "mta_sts" {
  for_each = local.mail_domains

  account_id = var.account_id
  zone_id    = each.value.zone_id
  hostname   = "mta-sts.${each.key}"
  service    = cloudflare_workers_script.mta_sts.script_name

  lifecycle {
    prevent_destroy = true
  }
}

# Created after the policy host answers, so senders never see a TXT without it.
resource "cloudflare_dns_record" "mail_mta_sts" {
  for_each = local.mail_domains

  zone_id = each.value.zone_id
  name    = "_mta-sts.${each.key}"
  type    = "TXT"
  content = "\"v=STSv1; id=${local.mta_sts_id}\""
  proxied = false
  ttl     = 1
  tags    = []

  depends_on = [cloudflare_workers_custom_domain.mta_sts]

  lifecycle {
    prevent_destroy = true
  }
}

# Created: lets the other domains send DMARC reports to local.report_mailbox.
# Their own _dmarc records (rua) are another zone each, not managed here yet.
resource "cloudflare_dns_record" "dmarc_report_authorization" {
  for_each = local.dmarc_reported_domains

  zone_id = var.zone_id
  name    = "${each.key}._report._dmarc.albandrieu.com"
  type    = "TXT"
  content = "\"v=DMARC1\""
  proxied = false
  ttl     = 1
  tags    = []

  lifecycle {
    prevent_destroy = true
  }
}
