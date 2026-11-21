"""Read-only, no-network unit contract for external mail and Nuclei privacy."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec and spec.loader
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


mail = module("public_mail", "scripts/security/check-public-mail-auth.py")
nuclei = module("public_nuclei", "scripts/security/minimize-external-nuclei.py")
head = module("public_head", "scripts/security/check-public-exposure-paths.py")


class ExternalPostureTest(unittest.TestCase):
    def setUp(self):
        # No unit test reaches the network: a test needing a policy patches it again.
        patcher = patch.object(mail, "fetch_policy", return_value=("UNVERIFIED", ""))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_domain_scope_is_explicit(self):
        rows = mail.read_scope(ROOT / "config/security/public-mail-domains.json")
        self.assertEqual([r["name"] for r in rows], list(mail.OWNED))  # the 20 zones
        uses = {r["name"]: r["mail_use"] for r in rows}
        self.assertEqual({n for n, use in uses.items() if use == "unverified"},
                         {"bababou.com", "dr-alban.com", "heoko.com", "papapou.com"})
        self.assertEqual(list(uses.values()).count("no-mail"), 14)
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "bad.json"
            file.write_text(json.dumps({"version": 1, "domains": [
                {"name": "evilalbandrieu.com", "mail_use": "sending",
                 "dkim_selectors": []}]}))
            with self.assertRaises(ValueError):
                mail.read_scope(file)

    def test_dmarc_subdomain_weakness_and_unknown_selectors(self):
        responses = {
            "albandrieu.com": ("NOERROR", ["v=spf1 -all"]),
            "_dmarc.albandrieu.com": (
                "NOERROR", ["v=DMARC1; p=reject; sp=none; pct=100"]),
            "_mta-sts.albandrieu.com": ("NXDOMAIN", []),
            "_smtp._tls.albandrieu.com": ("NXDOMAIN", []),
        }
        with patch.object(mail, "lookup", side_effect=lambda name: responses[name]):
            report = mail.audit({"name": "albandrieu.com", "mail_use": "sending",
                                 "dkim_selectors": []})["checks"]
        self.assertEqual(report["dmarc"], "REJECT_100")
        self.assertEqual(report["subdomain_dmarc"], "NON_STRICT")
        self.assertEqual(report["dkim"], "UNVERIFIED_NO_SELECTORS")

    def test_declared_no_mail_requires_null_mx_and_deny_all_spf(self):
        def fake_lookup(name, rrtype="TXT"):
            if rrtype == "MX":
                return "NOERROR", ["0 ."]
            if name == "bababou.com":
                return "NOERROR", ["v=spf1 -all"]
            return "NXDOMAIN", []
        with patch.object(mail, "lookup", side_effect=fake_lookup):
            result = mail.audit({"name": "bababou.com", "mail_use": "no-mail",
                                 "dkim_selectors": []})["checks"]
        self.assertEqual(result["null_mx"], "NULL_MX_DECLARED")
        self.assertEqual(result["no_mail_spf"], "DENY_ALL_ONLY")

    def test_personal_domains_declare_google_as_only_provider(self):
        rows = {r["name"]: r for r in mail.read_scope(
            ROOT / "config/security/public-mail-domains.json")}
        for name in ("albandrieu.com", "albanandrieu.com"):
            self.assertEqual(rows[name]["mail_provider"], "google")
            self.assertEqual(rows[name]["dkim_selectors"], ["google"])
        self.assertIn("mail2", rows["albandrieu.com"]["mx_subdomains"])
        self.assertNotIn("mail_provider", rows["bababou.com"])  # regime unchanged
        with tempfile.TemporaryDirectory() as folder:
            for bad in ({"mail_provider": "mtahosting"}, {"mx_subdomains": ["a.b"]},
                        {"mail_use": "no-mail"},
                        {"mx_exceptions": [{"label": "mail2", "target": "mx.example.net",
                                            "reason": "not a listed subdomain"}]},
                        {"mx_subdomains": ["mail2"], "mx_exceptions": [
                            {"label": "mail2", "target": "mx.example.net"}]}):
                file = Path(folder) / "bad.json"
                file.write_text(json.dumps({"version": 1, "domains": [{
                    "name": "albandrieu.com", "mail_use": "sending",
                    "mail_provider": "google", "dkim_selectors": [], **bad}]}))
                with self.assertRaises(ValueError):
                    mail.read_scope(file)

    GOOGLE_ROW = {"name": "albandrieu.com", "mail_use": "sending", "mail_provider": "google",
                  "dkim_selectors": ["google"], "mx_subdomains": ["mail2"]}
    # What the mta-sts Worker of terraform/cloudflare/mail.tofu serves for albandrieu.com.
    GOOGLE_STS = ("version: STSv1\r\nmode: testing\r\nmx: aspmx.l.google.com\r\n"
                  "mx: *.aspmx.l.google.com\r\nmx: smtp.google.com\r\nmax_age: 86400\r\n")

    @staticmethod
    def google_dns(overrides=None):
        dns = {
            ("albandrieu.com", "TXT"): ("NOERROR", ["v=spf1 include:_spf.google.com -all"]),
            ("_dmarc.albandrieu.com", "TXT"): ("NOERROR", [
                "v=DMARC1;p=reject;sp=reject;pct=100;adkim=s;aspf=s;"
                "rua=mailto:openclaw@albandrieu.com"]),
            ("google._domainkey.albandrieu.com", "TXT"): ("NOERROR", ["v=DKIM1;k=rsa;p=MIIB"]),
            ("_mta-sts.albandrieu.com", "TXT"): ("NOERROR", ["v=STSv1; id=20261120000000"]),
            ("_smtp._tls.albandrieu.com", "TXT"): ("NOERROR", [
                "v=TLSRPTv1; rua=mailto:technical@albandrieu.com"]),
            ("albandrieu.com", "MX"): ("NOERROR", ["1 smtp.google.com.", "1 aspmx.l.google.com.",
                                                   "5 alt1.aspmx.l.google.com."]),
            ("mail2.albandrieu.com", "MX"): ("NXDOMAIN", []),
        }
        dns.update(overrides or {})
        return lambda name, rrtype="TXT": dns[(name, rrtype)]

    def google_audit(self, dns=None, policy=None):
        with patch.object(mail, "lookup", side_effect=dns or self.google_dns()), \
                patch.object(mail, "fetch_policy", return_value=policy or ("OK", self.GOOGLE_STS)):
            return mail.audit(self.GOOGLE_ROW)

    def test_google_only_policy_holds_without_violation(self):
        result = self.google_audit()
        self.assertEqual(result["violations"], [])
        self.assertEqual(result["checks"]["mx_provider"], "GOOGLE_ONLY")
        self.assertEqual(result["checks"]["spf_provider"], "GOOGLE_ONLY_HARD_FAIL")
        self.assertEqual(result["checks"]["mta_sts_policy"], "TESTING_MX_MATCH")

    def test_soft_fail_third_party_mx_and_missing_tls_rpt_are_violations(self):
        drift = self.google_dns({
            ("albandrieu.com", "TXT"): ("NOERROR", ["v=spf1 include:_spf.google.com ~all"]),
            ("_dmarc.albandrieu.com", "TXT"): ("NOERROR", ["v=DMARC1;p=reject;pct=100"]),
            ("_smtp._tls.albandrieu.com", "TXT"): ("NXDOMAIN", []),
            ("mail2.albandrieu.com", "MX"): ("NOERROR", ["10 mx3.mtahosting.com."]),
        })
        result = self.google_audit(drift)
        self.assertEqual(result["violations"], [
            "dmarc_alignment", "dmarc_reporting", "mx_provider", "spf_provider", "tls_rpt"])
        self.assertEqual(result["checks"]["mx_provider"], "NON_GOOGLE_MX")
        # A look-alike host is not Google.
        lookalike = self.google_dns({("albandrieu.com", "MX"): (
            "NOERROR", ["1 aspmx.l.google.com.evil.example."])})
        self.assertEqual(self.google_audit(lookalike)["checks"]["mx_provider"], "NON_GOOGLE_MX")

    def test_mail2_project_honey_pot_mx_is_the_only_declared_exception(self):
        rows = mail.read_scope(ROOT / "config/security/public-mail-domains.json")
        exceptions = [(r["name"], x["label"], x["target"])
                      for r in rows for x in r.get("mx_exceptions", [])]
        self.assertEqual(exceptions, [("albandrieu.com", "mail2", "mx3.mtahosting.com")])
        row = {**self.GOOGLE_ROW, "mx_exceptions": [
            {"label": "mail2", "target": "mx3.mtahosting.com", "reason": "honeypot"}]}

        def mx(overrides):
            with patch.object(mail, "lookup", side_effect=self.google_dns(overrides)), \
                    patch.object(mail, "fetch_policy", return_value=("OK", self.GOOGLE_STS)):
                return mail.audit(row)["checks"]["mx_provider"]
        kept = ("NOERROR", ["10 mx3.mtahosting.com."])
        self.assertEqual(mx({("mail2.albandrieu.com", "MX"): kept}), "GOOGLE_ONLY")
        # Any other non-Google MX still fails: another target, or the apex.
        self.assertEqual(mx({("mail2.albandrieu.com", "MX"): (
            "NOERROR", ["10 mx3.mtahosting.com.", "20 mx4.mtahosting.com."])}), "NON_GOOGLE_MX")
        self.assertEqual(mx({("albandrieu.com", "MX"): kept}), "NON_GOOGLE_MX")

    def test_mta_sts_testing_policy_must_list_exactly_the_published_mx(self):
        def policy(text):
            return self.google_audit(policy=("OK", text))["checks"]["mta_sts_policy"]
        self.assertEqual(policy(self.GOOGLE_STS.replace("mx: smtp.google.com\r\n", "")),
                         "TESTING_MX_MISMATCH")  # a published MX is not covered
        self.assertEqual(policy(self.GOOGLE_STS + "mx: mx3.mtahosting.com\r\n"),
                         "TESTING_MX_MISMATCH")  # the policy lists an unpublished MX
        self.assertEqual(policy(self.GOOGLE_STS.replace("testing", "enforce")),
                         "ENFORCE_MX_MATCH")
        self.assertEqual(policy(self.GOOGLE_STS.replace("STSv1", "STSv2")), "INVALID_POLICY")
        self.assertEqual(policy("mode: testing\nmx: smtp.google.com\n"), "INVALID_POLICY")
        self.assertIn("mta_sts_policy", self.google_audit(
            policy=("OK", self.GOOGLE_STS.replace("testing", "enforce")))["violations"])
        # No policy host or no _mta-sts record is a violation; a failed fetch is not.
        self.assertEqual(self.google_audit(policy=("MISSING", ""))["violations"],
                         ["mta_sts_policy"])
        self.assertEqual(self.google_audit(self.google_dns({
            ("_mta-sts.albandrieu.com", "TXT"): ("NXDOMAIN", [])}))["violations"], ["mta_sts"])
        self.assertEqual(self.google_audit(policy=("UNVERIFIED", ""))["violations"], [])
        self.assertTrue(mail.mx_matches("*.aspmx.l.google.com", "alt1.aspmx.l.google.com"))
        self.assertFalse(mail.mx_matches("*.aspmx.l.google.com", "a.b.aspmx.l.google.com"))
        self.assertFalse(mail.mx_matches("*.aspmx.l.google.com", "aspmx.l.google.com"))

    def test_unresolved_google_checks_are_incomplete_not_violations(self):
        result = self.google_audit(lambda name, rrtype="TXT": ("UNVERIFIED", []),
                                   ("UNVERIFIED", ""))
        self.assertEqual(result["violations"], [])
        self.assertEqual(result["checks"]["mx_provider"], "UNVERIFIED")

    def test_provider_violation_fails_the_scan_with_exit_4(self):
        with tempfile.TemporaryDirectory() as folder:
            config, output = Path(folder) / "scope.json", Path(folder) / "out.json"
            config.write_text(json.dumps({"version": 1, "domains": [self.GOOGLE_ROW]}))
            drift = self.google_dns({("mail2.albandrieu.com", "MX"): (
                "NOERROR", ["10 mx3.mtahosting.com."])})
            argv = ["check", "--config", str(config), "--output", str(output)]
            with patch.object(mail, "lookup", side_effect=drift), \
                    patch.object(mail, "fetch_policy", return_value=("OK", self.GOOGLE_STS)), \
                    patch.object(mail.sys, "argv", argv):
                self.assertEqual(mail.main(), 4)
            report = json.loads(output.read_text())
        self.assertEqual(report["result"], "PROVIDER_POLICY_VIOLATION")
        self.assertNotIn("mtahosting", json.dumps(report))  # value-blind report
        self.assertNotIn("aspmx", json.dumps(report))

    def test_dmarc_reports_go_to_openclaw_with_external_authorization(self):
        auth = "bababou.com._report._dmarc.albandrieu.com"

        def reporting(name, dmarc, authorization=("NXDOMAIN", [])):
            dns = {"_dmarc." + name: ("NOERROR", [dmarc]), auth: authorization}
            with patch.object(mail, "lookup",
                              side_effect=lambda n, rrtype="TXT": dns.get(n, ("NXDOMAIN", []))):
                result = mail.audit({"name": name, "mail_use": "unverified",
                                     "dkim_selectors": []})
            return result["checks"]["dmarc_reporting"], "dmarc_reporting" in result["violations"]

        openclaw = "v=DMARC1; p=none; rua=mailto:openclaw@albandrieu.com"
        # The reporting domain itself needs no authorization record.
        self.assertEqual(reporting("albandrieu.com", openclaw)[0], "OPENCLAW_RUA_AUTHORIZED")
        self.assertEqual(reporting("bababou.com", openclaw, ("NOERROR", ["v=DMARC1"])),
                         ("OPENCLAW_RUA_AUTHORIZED", False))
        # Keeping the Cloudflare address next to openclaw (with a size limit) is fine.
        both = ("v=DMARC1; p=none; rua=mailto:x@dmarc-reports.cloudflare.net,"
                "mailto:openclaw@albandrieu.com!10m")
        self.assertEqual(reporting("bababou.com", both, ("NOERROR", ["v=DMARC1"]))[0],
                         "OPENCLAW_RUA_AUTHORIZED")
        self.assertEqual(reporting("bababou.com", openclaw),
                         ("EXTERNAL_AUTHORIZATION_MISSING", True))
        self.assertEqual(reporting("bababou.com", "v=DMARC1; p=none; rua=mailto:x@example.net"),
                         ("OPENCLAW_RUA_MISSING", True))
        self.assertEqual(reporting("bababou.com", openclaw, ("UNVERIFIED", [])),
                         ("UNVERIFIED", False))  # incomplete, never a violation

    def test_zones_without_mail_need_null_mx_deny_all_spf_and_dmarc_reject(self):
        hardened = {
            ("heoko.net", "MX"): ("NOERROR", ["0 ."]),
            ("heoko.net", "TXT"): ("NOERROR", ["v=spf1 -all"]),
            ("_dmarc.heoko.net", "TXT"): ("NOERROR", [
                "v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s; "
                "rua=mailto:openclaw@albandrieu.com; ruf=mailto:openclaw@albandrieu.com"]),
            ("heoko.net._report._dmarc.albandrieu.com", "TXT"): ("NOERROR", ["v=DMARC1"]),
        }

        def audit(overrides=None):
            dns = {**hardened, **(overrides or {})}
            with patch.object(mail, "lookup", side_effect=lambda n, rrtype="TXT":
                              dns.get((n, rrtype), ("NXDOMAIN", []))):
                return mail.audit({"name": "heoko.net", "mail_use": "no-mail",
                                   "dkim_selectors": []})["violations"]
        self.assertEqual(audit(), [])  # no TLS-RPT nor MTA-STS needed without mail
        self.assertEqual(audit({("heoko.net", "MX"): ("NXDOMAIN", []),
                                ("heoko.net", "TXT"): ("NXDOMAIN", [])}),
                         ["no_mail_spf", "null_mx"])
        self.assertEqual(audit({("_dmarc.heoko.net", "TXT"): ("NOERROR", [
            "v=DMARC1; p=none; rua=mailto:openclaw@albandrieu.com"])}),
            ["dmarc", "subdomain_dmarc"])

    def test_dns_failure_never_claimed_missing(self):
        with patch.object(mail, "lookup", return_value=("UNVERIFIED", [])):
            report = mail.audit({"name": "bababou.com", "mail_use": "unverified",
                                 "dkim_selectors": []})["checks"]
        self.assertEqual(report["spf"], "UNVERIFIED")
        self.assertEqual(report["dmarc"], "UNVERIFIED")

    def test_head_probes_never_claim_exposure_from_status_alone(self):
        self.assertEqual(head.classify(200, 200), "FALLBACK_2XX_UNVERIFIED")
        self.assertEqual(head.classify(200, 404), "REVIEW_2XX_NOT_PROVEN")
        self.assertEqual(head.classify(403, 404), "DENIED_OBSERVED")
        self.assertEqual(head.classify(302, 404), "REDIRECT_UNVERIFIED")
        self.assertEqual(head.classify(None, 404), "UNVERIFIED")
        for expected in ("/.env", "/.git/config", "/terraform.tfstate",
                         "/metrics", "/api", "/wp-login.php"):
            self.assertIn(expected, head.PATHS)

    def test_raw_nuclei_secrets_are_never_published(self):
        with tempfile.TemporaryDirectory() as folder:
            raw, safe = Path(folder) / "raw.jsonl", Path(folder) / "safe.jsonl"
            raw.write_text(json.dumps({
                "host": "famp-albandrieu.albandrieu.com",
                "template-id": "git-config", "info": {"severity": "high"},
                "matcher-name": "git-config",
                "curl-command": "Authorization: secret",
                "extracted-results": ["PASSWORD=veryprivate"],
                "matched-at": "https://host/.env?token=abc"
            }) + "\n")
            self.assertEqual(nuclei.sanitize(raw, safe), 1)
            content = safe.read_text()
            self.assertNotIn("PASSWORD", content)
            self.assertNotIn("Authorization", content)
            self.assertNotIn("token=abc", content)
            self.assertEqual(len(json.loads(content)), 4)


if __name__ == "__main__":
    unittest.main()
