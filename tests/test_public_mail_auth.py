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

    def test_dns_failure_never_claimed_missing(self):
        with patch.object(mail, "lookup", return_value=("UNVERIFIED", [])):
            report = mail.audit({"name": "bababou.com", "mail_use": "unverified",
                                 "dkim_selectors": []})["checks"]
        self.assertEqual(report["spf"], "UNVERIFIED")
        self.assertEqual(report["dmarc"], "UNVERIFIED")

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
