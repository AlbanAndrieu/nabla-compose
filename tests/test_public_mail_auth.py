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
    def test_domain_scope_is_explicit(self):
        rows = mail.read_scope(ROOT / "config/security/public-mail-domains.json")
        self.assertEqual({r["name"] for r in rows}, {
            "albandrieu.com", "albanandrieu.com", "bababou.com"})
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
                        {"mail_use": "no-mail"}):
                file = Path(folder) / "bad.json"
                file.write_text(json.dumps({"version": 1, "domains": [{
                    "name": "albandrieu.com", "mail_use": "sending",
                    "mail_provider": "google", "dkim_selectors": [], **bad}]}))
                with self.assertRaises(ValueError):
                    mail.read_scope(file)

    GOOGLE_ROW = {"name": "albandrieu.com", "mail_use": "sending", "mail_provider": "google",
                  "dkim_selectors": ["google"], "mx_subdomains": ["mail2"]}

    @staticmethod
    def google_dns(overrides=None):
        dns = {
            ("albandrieu.com", "TXT"): ("NOERROR", ["v=spf1 include:_spf.google.com -all"]),
            ("_dmarc.albandrieu.com", "TXT"): ("NOERROR", [
                "v=DMARC1;p=reject;sp=reject;pct=100;adkim=s;aspf=s"]),
            ("google._domainkey.albandrieu.com", "TXT"): ("NOERROR", ["v=DKIM1;k=rsa;p=MIIB"]),
            ("_mta-sts.albandrieu.com", "TXT"): ("NXDOMAIN", []),
            ("_smtp._tls.albandrieu.com", "TXT"): ("NOERROR", [
                "v=TLSRPTv1; rua=mailto:technical@albandrieu.com"]),
            ("albandrieu.com", "MX"): ("NOERROR", ["1 smtp.google.com.",
                                                   "5 alt1.aspmx.l.google.com."]),
            ("mail2.albandrieu.com", "MX"): ("NXDOMAIN", []),
        }
        dns.update(overrides or {})
        return lambda name, rrtype="TXT": dns[(name, rrtype)]

    def test_google_only_policy_holds_without_violation(self):
        with patch.object(mail, "lookup", side_effect=self.google_dns()):
            result = mail.audit(self.GOOGLE_ROW)
        self.assertEqual(result["violations"], [])
        self.assertEqual(result["checks"]["mx_provider"], "GOOGLE_ONLY")
        self.assertEqual(result["checks"]["spf_provider"], "GOOGLE_ONLY_HARD_FAIL")

    def test_soft_fail_third_party_mx_and_missing_tls_rpt_are_violations(self):
        drift = self.google_dns({
            ("albandrieu.com", "TXT"): ("NOERROR", ["v=spf1 include:_spf.google.com ~all"]),
            ("_dmarc.albandrieu.com", "TXT"): ("NOERROR", ["v=DMARC1;p=reject;pct=100"]),
            ("_smtp._tls.albandrieu.com", "TXT"): ("NXDOMAIN", []),
            ("mail2.albandrieu.com", "MX"): ("NOERROR", ["10 mx3.mtahosting.com."]),
        })
        with patch.object(mail, "lookup", side_effect=drift):
            result = mail.audit(self.GOOGLE_ROW)
        self.assertEqual(result["violations"], [
            "dmarc_alignment", "mx_provider", "spf_provider", "tls_rpt"])
        self.assertEqual(result["checks"]["mx_provider"], "NON_GOOGLE_MX")
        # A look-alike host is not Google.
        lookalike = self.google_dns({("albandrieu.com", "MX"): (
            "NOERROR", ["1 aspmx.l.google.com.evil.example."])})
        with patch.object(mail, "lookup", side_effect=lookalike):
            self.assertEqual(mail.audit(self.GOOGLE_ROW)["checks"]["mx_provider"],
                             "NON_GOOGLE_MX")

    def test_unresolved_google_checks_are_incomplete_not_violations(self):
        with patch.object(mail, "lookup", return_value=("UNVERIFIED", [])):
            result = mail.audit(self.GOOGLE_ROW)
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
                    patch.object(mail.sys, "argv", argv):
                self.assertEqual(mail.main(), 4)
            report = json.loads(output.read_text())
        self.assertEqual(report["result"], "PROVIDER_POLICY_VIOLATION")
        self.assertNotIn("mtahosting", json.dumps(report))  # value-blind report

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
