"""Export contract: only de-identified Amass aggregates reach /media/www."""
import json
from unittest.mock import patch
from pathlib import Path
import runpy
import stat
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PUBLISH = ROOT / "scripts/security/publish-ctem-web-summary.py"
MODULE = runpy.run_path(str(PUBLISH))
SCOPE = json.loads((ROOT / "config/security/public-mail-domains.json").read_text())
DOMAINS = sorted(row["name"] for row in SCOPE["domains"])
CATEGORIES = sorted(MODULE["EXPECTED_CATEGORIES"])


def sample():
    categories = {cat: 0 for cat in CATEGORIES}
    categories["MATCHED_PUBLIC_INTENT"] = 6
    return {
        "schema_version": 1, "scanner": "amass", "scanner_version": "5.1.3",
        "scan_mode": "active", "asset_database": "shared-postgresql/assetdb",
        "vantage": "truenas-internal", "status": "OBSERVED_NOT_CERTIFIED",
        "checked_at": "2026-11-21T09:00:00+00:00",
        "scope": DOMAINS, "counts": {
            domain: 6 if index == 0 else 0
            for index, domain in enumerate(DOMAINS)
        },
        "catalogReconciliation": {
            "status": "OBSERVED_NOT_CERTIFIED",
            "catalogRevision": "sha256:" + "a"*64,
            "candidateMatchCounts": categories,
        },
        "candidates": [{"hostname": "private." + DOMAINS[0]}],
    }


class PublicCtemExportContract(unittest.TestCase):
    def test_only_aggregates_no_hostnames_or_raw_private_data(self):
        public = MODULE["validate"](sample(), set(DOMAINS))
        output = json.dumps(public) + MODULE["html_page"](public)
        self.assertEqual(public["domains_in_scope"], len(DOMAINS))
        self.assertEqual(public["candidate_count"], 6)
        self.assertIn("noindex,nofollow", output)
        self.assertNotIn("private.", output)
        self.assertNotIn("candidate", str(public.get("candidates", [])))
        for name in DOMAINS:
            self.assertNotIn(name, output)
        for forbidden in ("catalogRevision", "entityRef", "catalogMatches",
                          "private_output", "/mnt/cpool/ctem/amass/reports"):
            self.assertNotIn(forbidden, output)

    def test_reject_incomplete_and_wrong_vantage(self):
        for attr, value in (
            ("status", "ENGINE_NOT_READY"),
            ("vantage", "external-github-hosted"),
            ("scan_mode", "passive"),
            ("asset_database", "ephemeral-external"),
        ):
            with self.subTest(attr=attr):
                doc = sample()
                doc[attr] = value
                with self.assertRaises(ValueError):
                    MODULE["validate"](doc, set(DOMAINS))

    def test_reject_scope_and_reconciliation_mismatch(self):
        doc = sample()
        doc["scope"] = ["example.net"]
        with self.assertRaises(ValueError):
            MODULE["validate"](doc, set(DOMAINS))
        doc = sample()
        doc["catalogReconciliation"]["candidateMatchCounts"]["MATCHED_PUBLIC_INTENT"] = 5
        with self.assertRaises(ValueError):
            MODULE["validate"](doc, set(DOMAINS))

    def test_private_input_rejects_world_readable_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "summary.json"
            source.write_text(json.dumps(sample()))
            source.chmod(0o644)
            with self.assertRaises(ValueError):
                MODULE["read_private"](source, require_root=False)
            source.chmod(0o600)
            self.assertEqual(MODULE["read_private"](source, require_root=False)["scanner"], "amass")
            alias = Path(temp) / "alias.json"
            alias.symlink_to(source)
            with self.assertRaises(ValueError):
                MODULE["read_private"](alias, require_root=False)

    def test_atomic_publish_and_no_symlink_target(self):
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            # CodeQL: temporary report starts private (0600), final aggregate
            # alone becomes world-readable (0644) for the controlled web root.
            with patch.object(MODULE["os"], "open", wraps=MODULE["os"].open) as opened:
                MODULE["atomic_publish"](d, "amass-summary.json", '{"status":"example"}')
            staged = [call for call in opened.call_args_list
                      if ".amass-summary.json.tmp-" in str(call.args[0])]
            self.assertEqual(len(staged), 1)
            self.assertEqual(staged[0].args[2], 0o600)
            report = d / "amass-summary.json"
            self.assertEqual(stat.S_IMODE(report.stat().st_mode), 0o644)
            self.assertIn("example", report.read_text())
            report.unlink()
            report.symlink_to(d / "nowhere")
            with self.assertRaises(ValueError):
                MODULE["atomic_publish"](d, "amass-summary.json", "other")

    def test_runtime_publication_off_by_default(self):
        runner = (ROOT / "scripts/security/run-ctem-amass-truenas.sh").read_text()
        cron = (ROOT / "scripts/cron.sh").read_text()
        self.assertIn("CTEM_WEB_PUBLISH_APPROVED", runner)
        self.assertIn("publish-ctem-web-summary.py", runner)
        self.assertIn("NABLA_CRON_CTEM_WEB_ENABLED:-false", cron)
        self.assertIn("CTEM_WEB_PUBLISH_APPROVED", cron)
        self.assertIn("/mnt/cpool/www/reports/ctem", PUBLISH.read_text())


if __name__ == "__main__":
    unittest.main()
