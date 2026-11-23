# Mail hardening of the 20 zones of the account (owner decisions, 20/11/2026):
# - Google Workspace alone sends and receives for albandrieu.com and
#   albanandrieu.com: apex SPF hard-failed (mail2's Project Honey Pot MX is
#   the one declared exception of the scan);
# - 23/11/2026: the four other Google zones get SPF -all too, and every DMARC
#   still at p=none moves to p=quarantine (reject stays reject);
# - every zone reports DMARC to one mailbox, authorized by albandrieu.com;
# - zones without mail get a null MX, SPF -all and DMARC reject;
# - zones receiving mail through Google get TLS-RPT and MTA-STS in testing
#   mode, the policy served by a Cloudflare Worker, not the homelab.
# MX and DKIM stay dashboard-owned. The external scan
# (scripts/security/check-public-mail-auth.py) enforces the same policy over
# config/security/public-mail-domains.json. CAA is proposed only (README).

locals {
  report_mailbox = "openclaw@albandrieu.com"
  mail_zone_ids = merge(var.mail_zone_ids, {
    "albandrieu.com"   = var.zone_id
    "albanandrieu.com" = var.albanandrieu_zone_id
  })
  # Google-only domains: an existing apex SPF is imported (~all on 23/11),
  # then hard-failed; heoko.com and papapou.com published none.
  mail_domains = {
    "albandrieu.com"   = { spf_ttl = 1 }
    "albanandrieu.com" = { spf_ttl = 3600 }
    "bababou.com"      = { spf_ttl = 3600 }
    "dr-alban.com"     = { spf_ttl = 3600 }
    "heoko.com"        = { spf_ttl = 1 }
    "papapou.com"      = { spf_ttl = 1 }
  }
  # Zones receiving mail through Google, with exactly their published MX: the
  # scan compares the served MTA-STS policy with them.
  mta_sts_mx = {
    "albandrieu.com"   = ["aspmx.l.google.com", "*.aspmx.l.google.com", "smtp.google.com"]
    "albanandrieu.com" = ["aspmx.l.google.com", "*.aspmx.l.google.com"]
    "bababou.com"      = ["aspmx.l.google.com", "*.aspmx.l.google.com"]
    "dr-alban.com"     = ["aspmx.l.google.com", "*.aspmx.l.google.com"]
    "heoko.com"        = ["smtp.google.com"]
    "papapou.com"      = ["smtp.google.com"]
  }
  # No MX, no SPF and no DMARC on 20/11/2026.
  no_mail_domains = toset([
    "bababou.net", "eokoo.net", "eokou.com", "heoko.net", "heoko.org", "heokoo.com",
    "heokoo.net", "heokoo.org", "heokou.com", "heokou.net", "heokou.org", "papapou.net",
    "papapou.org", "papoyou.net",
  ])
  # The DMARC record of every zone. Existing policies keep their tags, only
  # rua/ruf move; these four already publish one and are imported (imports.tofu).
  dmarc_existing = ["albandrieu.com", "albanandrieu.com", "bababou.com", "dr-alban.com"]
  dmarc_records = merge(
    { for domain in local.no_mail_domains : domain => "v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s; rua=mailto:${local.report_mailbox}; ruf=mailto:${local.report_mailbox}" },
    {
      "albandrieu.com"   = "v=DMARC1;p=reject;sp=reject;pct=100;adkim=s;aspf=s;rua=mailto:${local.report_mailbox};ruf=mailto:${local.report_mailbox};fo=1;ri=86400"
      "albanandrieu.com" = "v=DMARC1;p=reject;sp=reject;pct=100;adkim=s;aspf=s;rua=mailto:${local.report_mailbox};ruf=mailto:${local.report_mailbox};fo=1;ri=86400"
      # Cloudflare DMARC Management keeps its reports next to the mailbox.
      "bababou.com"  = "v=DMARC1; p=quarantine; rua=mailto:6bb8350e45534cc29163df40b1955713@dmarc-reports.cloudflare.net,mailto:${local.report_mailbox}; ruf=mailto:${local.report_mailbox}" # gitleaks:allow
      "dr-alban.com" = "v=DMARC1; p=quarantine; rua=mailto:b7741e45cb634c37bdad842ebb976523@dmarc-reports.cloudflare.net,mailto:${local.report_mailbox}; ruf=mailto:${local.report_mailbox}" # gitleaks:allow
      # Mail in use (Google MX and DKIM): quarantine, reject after clean reports.
      "heoko.com"   = "v=DMARC1; p=quarantine; rua=mailto:${local.report_mailbox}; ruf=mailto:${local.report_mailbox}; fo=1"
      "papapou.com" = "v=DMARC1; p=quarantine; rua=mailto:${local.report_mailbox}; ruf=mailto:${local.report_mailbox}; fo=1"
    },
  )
  # RFC 7489 7.1: albandrieu.com accepts the reports of every other zone.
  dmarc_reported_domains = toset([for domain in keys(local.dmarc_records) : domain if domain != "albandrieu.com"])
  # RFC 8461: a new id with every policy change. enforce comes after weeks of
  # clean TLS-RPT reports (docs/roadmap.md).
  mta_sts_id = "20261120000000"
  mta_sts_policies = {
    for domain, mx in local.mta_sts_mx : "mta-sts.${domain}" => join("\r\n", concat(
      ["version: STSv1", "mode: testing"],
      [for pattern in mx : "mx: ${pattern}"],
      ["max_age: 86400", ""],
    ))
  }
}

# Imported where published (imports.tofu: only ~all becomes -all), else created.
resource "cloudflare_dns_record" "mail_spf" {
  for_each = local.mail_domains

  zone_id = local.mail_zone_ids[each.key]
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

# Four imported (only rua/ruf change), sixteen created.
resource "cloudflare_dns_record" "mail_dmarc" {
  for_each = local.dmarc_records

  zone_id = local.mail_zone_ids[each.key]
  name    = "_dmarc.${each.key}"
  type    = "TXT"
  content = "\"${each.value}\""
  proxied = false
  ttl     = 1
  tags    = []

  lifecycle {
    prevent_destroy = true
    # Two DMARC records void the policy: an existing one is imported, never doubled.
    precondition {
      condition     = !contains(local.dmarc_existing, each.key) || contains(keys(var.mail_dmarc_record_ids), each.key)
      error_message = "${each.key} already publishes DMARC: set its record id in mail_dmarc_record_ids."
    }
  }
}

# Created: RFC 7505 null MX and a deny-all SPF on the zones without mail.
resource "cloudflare_dns_record" "no_mail_mx" {
  for_each = local.no_mail_domains

  zone_id  = local.mail_zone_ids[each.key]
  name     = each.key
  type     = "MX"
  content  = "."
  priority = 0
  proxied  = false
  ttl      = 1
  tags     = []

  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_dns_record" "no_mail_spf" {
  for_each = local.no_mail_domains

  zone_id = local.mail_zone_ids[each.key]
  name    = each.key
  type    = "TXT"
  content = "\"v=spf1 -all\""
  proxied = false
  ttl     = 1
  tags    = []

  lifecycle {
    prevent_destroy = true
  }
}

# Created: no TLS-RPT record exists. Reports go to the shared report mailbox.
resource "cloudflare_dns_record" "mail_tls_rpt" {
  for_each = local.mta_sts_mx

  zone_id = local.mail_zone_ids[each.key]
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

# Created: the policy host. No route, origin or binding; one script serves
# every custom domain (Cloudflare creates their DNS record and certificate).
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
  for_each = local.mta_sts_mx

  account_id = var.account_id
  zone_id    = local.mail_zone_ids[each.key]
  hostname   = "mta-sts.${each.key}"
  service    = cloudflare_workers_script.mta_sts.script_name

  lifecycle {
    prevent_destroy = true
  }
}

# Created after the policy host answers, so senders never see a TXT without it.
resource "cloudflare_dns_record" "mail_mta_sts" {
  for_each = local.mta_sts_mx

  zone_id = local.mail_zone_ids[each.key]
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

# Created: lets every other zone send DMARC reports to local.report_mailbox.
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
