"""Offline contracts for the import-first Cloudflare OpenTofu unit."""

import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
TF = ROOT / "terraform/cloudflare"
CAPTURE = ROOT / "scripts/cloudflare/capture-homelab-tofu.sh"


def module_source() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(TF.glob("*.tofu")))


class CloudflareContract(unittest.TestCase):
    def test_provider_is_pinned_and_token_stays_in_environment(self):
        source = module_source()
        self.assertRegex(source, r'version\s*=\s*"= 5\.\d+\.\d+"')
        self.assertIn('provider "cloudflare" {}', source)
        self.assertNotRegex(source, r"(?i)\b(api_token|api_key)\s*=")

    def test_access_application_names_are_the_kebab_case_resource_names(self):
        # One naming rule for every Access application shown in the dashboard.
        source = module_source()
        apps = re.findall(
            r'resource "cloudflare_zero_trust_access_application" "(\w+)" \{.*?\n  name\s+= "([^"]+)"',
            source,
            flags=re.S,
        )
        self.assertGreaterEqual(len(apps), 14)
        for resource, name in apps:
            with self.subTest(resource=resource):
                self.assertEqual(name, resource.replace("_", "-"))

    def test_every_resource_is_imported_first(self):
        imports = (TF / "imports.tofu").read_text(encoding="utf-8")
        expected = {
            "cloudflare_zero_trust_tunnel_cloudflared_config.homelab":
                '"${var.account_id}/${var.tunnel_id}"',
            "cloudflare_dns_record.fastapi_sample":
                '"${var.zone_id}/${var.fastapi_sample_dns_record_id}"',
            "cloudflare_zero_trust_access_application.fastapi_sample":
                '"accounts/${var.account_id}/${var.fastapi_sample_access_application_id}"',
            "cloudflare_zero_trust_access_application.fastapi_sample_api":
                '"accounts/${var.account_id}/${var.fastapi_sample_api_access_application_id}"',
        }
        for address, import_id in expected.items():
            self.assertRegex(
                imports,
                rf"to = {re.escape(address)}\n\s*id = {re.escape(import_id)}",
            )
        # Resources that never existed in the dashboard: created by the module, never imported.
        created = {
            f"cloudflare_zero_trust_access_application.{name}"
            for name in (
                "keycloak_oidc", "joplin", "vaultwarden_admin",
                "affine", "freshrss", "plumber_api", "immich", "ha", "famp_albandrieu",
                "fastapi_github_webhook", "honeypot_login", "truenas_admin",
            )
        } | {"cloudflare_zero_trust_access_policy.freshrss_site",
             "cloudflare_dns_record.mail_tls_rpt", "cloudflare_dns_record.mail_mta_sts",
             "cloudflare_workers_script.mta_sts", "cloudflare_workers_custom_domain.mta_sts",
             "cloudflare_dns_record.dmarc_report_authorization",
             "cloudflare_dns_record.no_mail_mx", "cloudflare_dns_record.no_mail_spf"}
        resources = re.findall(r'resource "(\w+)" "(\w+)"', module_source())
        for kind, name in resources:
            if f"{kind}.{name}" in {"cloudflare_dns_record.home", "cloudflare_dns_record.mail_spf",
                                    "cloudflare_dns_record.mail_dmarc"}:
                self.assertIn(f"to       = {kind}.{name}[each.key]", imports)
                continue
            if f"{kind}.{name}" in created:
                self.assertNotIn(f"to = {kind}.{name}\n", imports)
                continue
            self.assertIn(f"to = {kind}.{name}\n", imports)

    def test_mta_sts_is_testing_and_served_by_a_static_worker(self):
        # Owner decision (20/11/2026): testing first, enforce after clean TLS-RPT reports.
        mail = (TF / "mail.tofu").read_text(encoding="utf-8")
        self.assertIn('["version: STSv1", "mode: testing"]', mail)
        self.assertIn('["max_age: 86400", ""]', mail)
        self.assertIn('"albandrieu.com"   = ["aspmx.l.google.com", "*.aspmx.l.google.com", '
                      '"smtp.google.com"]', mail)
        self.assertIn('"heoko.com"        = ["smtp.google.com"]', mail)
        self.assertIn("depends_on = [cloudflare_workers_custom_domain.mta_sts]", mail)
        worker = (TF / "mta-sts-worker.js.tftpl").read_text(encoding="utf-8")
        self.assertEqual(worker.count("fetch("), 1)  # the handler only: no outbound call

    def test_the_twenty_zones_follow_the_mail_scan_scope(self):
        # Owner decision (20/11/2026): harden every zone of the account through OpenTofu.
        mail = (TF / "mail.tofu").read_text(encoding="utf-8")
        ids = (TF / "mail-record-ids.auto.tfvars").read_text(encoding="utf-8")
        rows = json.loads((ROOT / "config/security/public-mail-domains.json").read_text())["domains"]
        names = {row["name"] for row in rows}
        no_mail = {row["name"] for row in rows if row["mail_use"] == "no-mail"}

        def keys(text, block):
            return set(re.findall(r'"([a-z0-9.-]+)"\s*=', text.split(block, 1)[1].split("}", 1)[0]))
        self.assertEqual(keys(ids, "mail_zone_ids = {") | {"albandrieu.com", "albanandrieu.com"},
                         names)
        listed = mail.split("no_mail_domains = toset([", 1)[1].split("])", 1)[0]
        self.assertEqual(set(re.findall(r'"([a-z0-9.-]+)"', listed)), no_mail)
        # Every zone with mail gets MTA-STS and an explicit DMARC; the others a
        # generated DMARC reject, a null MX and SPF -all.
        self.assertEqual(keys(mail, "mta_sts_mx = {"), names - no_mail)
        explicit = set(re.findall(r'^\s*"([a-z0-9.-]+)"\s*=\s*"v=DMARC1', mail, re.M))
        self.assertEqual(explicit, names - no_mail)
        self.assertEqual(keys(ids, "mail_dmarc_record_ids = {"),
                         set(re.findall(r'"([a-z0-9.-]+)"', mail.split("dmarc_existing = [", 1)[1]
                                                                .split("]", 1)[0])))
        dmarc = re.findall(r'"v=DMARC1;\s*p=[^"\n]*"', mail)  # policies, not authorizations
        self.assertEqual(len(dmarc), 1 + len(names - no_mail))  # generated + explicit
        for record in dmarc:
            self.assertIn("rua=mailto:", record)
            self.assertIn("mailto:${local.report_mailbox}", record)
        self.assertIn('report_mailbox = "openclaw@albandrieu.com"', mail)
        self.assertIn('content = "\\"v=TLSRPTv1; rua=mailto:${local.report_mailbox}\\""', mail)
        self.assertIn('content  = "."\n  priority = 0', mail)  # RFC 7505 null MX
        self.assertIn('content = "\\"v=spf1 -all\\""', mail)

    def test_bypassed_joplin_route_is_refused_until_its_app_runs(self):
        # The joplin Access app is "Everyone bypass"; with no Joplin App behind
        # :22300 (H08), any listener there would be public without auth.
        tunnel = (TF / "tunnel.tofu").read_text(encoding="utf-8")
        route = re.search(
            r'hostname\s*=\s*"joplin\.albandrieu\.com".*?service\s*=\s*"([^"]*)"',
            tunnel, re.S,
        )
        self.assertIsNotNone(route)
        self.assertEqual(route.group(1), "http_status:404")

    def test_bypassed_honeypot_route_reaches_only_the_honeypot_app(self):
        # Owner decision, 20/11/2026: the trap is public behind "Everyone bypass".
        # The route targets the published port of the honeypot App (running on
        # TrueNAS since 21/11/2026), nothing else.
        tunnel = (TF / "tunnel.tofu").read_text(encoding="utf-8")
        route = tunnel.split('hostname = "login.albandrieu.com"', 1)[1].split("},", 1)[0]
        self.assertIn(
            'service = var.honeypot_tunnel_via_traefik ? "https://traefik:443" : "http://172.17.0.24:31090"',
            route,
        )
        self.assertNotIn("no_tls_verify", route)
        opts = (TF / "variables.tofu").read_text(encoding="utf-8")
        self.assertIn('variable "honeypot_tunnel_via_traefik"', opts)
        self.assertIn("default     = false", opts.split('variable "honeypot_tunnel_via_traefik"', 1)[1])
        self.assertNotIn('"honeypot-albandrieu.albandrieu.com"', tunnel)
        access = (TF / "access.tofu").read_text(encoding="utf-8")
        block = access.split('"honeypot_login"', 1)[1].split("\nresource ", 1)[0]
        self.assertIn("access_policy_everyone_bypass_id", block)
        self.assertIn("app_launcher_visible = false", block)
        self.assertIn("cloudflare_zero_trust_access_application.honeypot_login", tunnel)

    def test_free_ptr_forward_a_requires_safe_import_or_verified_creation(self):
        dns = (TF / "dns.tofu").read_text(encoding="utf-8")
        variables = (TF / "variables.tofu").read_text(encoding="utf-8")
        imports = (TF / "imports.tofu").read_text(encoding="utf-8")
        self.assertIn('resource "cloudflare_dns_record" "home"', dns)
        self.assertIn('"home.albandrieu.com" = "82.66.4.247"', dns)
        self.assertIn('type                    = "A"', dns)
        self.assertIn("proxied                 = false", dns)
        self.assertIn("for_each = local.home_dns_a_enabled", dns)
        self.assertIn('home_dns_a_record_id != "" || var.home_dns_a_create_approved', dns)
        self.assertIn('default     = ""', variables)
        self.assertIn("default     = false", variables)
        self.assertIn('for_each = var.home_dns_a_record_id != ""', imports)
        self.assertIn("prevent_destroy = true", dns)
        self.assertIn("local.tunnel_hostnames", dns)
        self.assertIn("local.workstation_tunnel_hostnames", dns)

    def test_postgres_is_not_published(self):
        # Internal-only since 2026-11-10; its CNAME was destroyed on 2026-11-11.
        source = module_source()
        self.assertNotIn('hostname       = "postgres.albandrieu.com"', source)
        self.assertNotIn("tcp://172.17.0.24:5432", source)
        ids = (ROOT / "terraform/cloudflare/dns-record-ids.auto.tfvars").read_text()
        self.assertNotIn("postgres.albandrieu.com", ids)

    def test_declared_resources_cannot_be_destroyed(self):
        source = module_source()
        self.assertEqual(
            len(re.findall(r'^resource "', source, re.MULTILINE)),
            source.count("prevent_destroy = true"),
        )

    def test_keycloak_bypass_never_covers_the_master_realm(self):
        source = (TF / "access.tofu").read_text(encoding="utf-8")
        block = source.split('"keycloak_oidc"', 1)[1].split("\nresource ", 1)[0]
        self.assertIn("access_policy_everyone_bypass_id", block)
        self.assertNotRegex(block, r'uri\s*=\s*"keycloak\.albandrieu\.com(/realms/master)?/?"')

    def test_terragrunt_inherits_private_garage_state(self):
        source = (ROOT / "infrastructure/cloudflare/terragrunt.hcl").read_text()
        self.assertIn('include "root"', source)
        self.assertIn('find_in_parent_folders("terraform/cloudflare")', source)
        self.assertFalse(re.search(r"(?i)(token|password|secret)\s*=", source))

    def test_capture_is_read_only_and_hides_the_token(self):
        script = CAPTURE.read_text(encoding="utf-8")
        self.assertNotRegex(script, r"(?i)-X\b|--request|\b(POST|PUT|PATCH|DELETE)\b")
        self.assertNotRegex(script, r"(?m)^\s*tofu\b.*\b(apply|import|state)\b")
        self.assertIn("-H @-", script)
        self.assertIn("-generate-config-out=generated.tofu", script)
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/terraform/cloudflare/generated.tofu", gitignore)


if __name__ == "__main__":
    unittest.main()
