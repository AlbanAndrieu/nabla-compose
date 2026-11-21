"""Offline CTEM report persistence and reviewed DefectDojo import contracts."""
from datetime import datetime, timezone
import json
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
STORE = runpy.run_path(str(ROOT / "scripts/security/store-ctem-summary.py"))
PROJECT = runpy.run_path(str(ROOT / "scripts/security/project-ctem-mail-findings.py"))
VALIDATE = runpy.run_path(str(ROOT / "scripts/security/validate-defectdojo-report.py"))
REVISION = "sha256:" + "a" * 64
OWNED = sorted(
    row["name"] for row in json.loads(
        (ROOT / "config/security/public-mail-domains.json").read_text(encoding="utf-8")
    )["domains"]
)
APPROVED = set(json.loads(
    (ROOT / "config/security/defectdojo-allowed-imports.json").read_text(encoding="utf-8")
)["producers"]["ctem-mail"]["hosts"])


class CtemReportPipelineTests(unittest.TestCase):
    @staticmethod
    def amass():
        return {
            "schema_version": 1, "scanner": "amass",
            "scan_mode": "active", "checked_at": "2026-11-21T01:00:00+00:00",
            "status": "OBSERVED_NOT_CERTIFIED",
            "counts": {domain: (5 if domain == "albandrieu.com" else 0) for domain in OWNED},
            "rejected_count": 0,
            "catalogReconciliation": {
                "catalogRevision": REVISION, "catalogEntityCount": 210,
                "catalogLanOnlyPolicyConflicts": 1,
                "candidateMatchCounts": {
                    "MATCHED_PUBLIC_INTENT": 2, "LAN_ONLY_POLICY_REVIEW": 1,
                    "NON_PUBLIC_INTENT_REVIEW": 0, "AMBIGUOUS_ENTITY_REVIEW": 0,
                    "UNMAPPED_REVIEW": 2,
                },
            },
        }

    @staticmethod
    def mail():
        rows = {
            name: {
                "domain": name, "spf_valid": True,
                "dmarc_valid": True, "dmarc_p": "reject",
            }
            for name in OWNED
        }
        rows["albandrieu.com"]["spf_valid"] = False
        rows["albanandrieu.com"]["dmarc_p"] = "none"
        return {
            "checked_at": "2026-11-21T01:00:00+00:00",
            "scope": OWNED,
            "checkdmarc_version": "6.0.3",
            "checkdmarc": {
                "status": "OBSERVED_NOT_CERTIFIED",
                "results": list(rows.values()),
            },
        }

    def test_amass_metadata_receipt_no_names(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "summary.json"
            p.write_text(json.dumps(self.amass()))
            obj, digest, encoded = STORE["validate_receipt"]("amass", p)
            self.assertEqual(obj["status"], "OBSERVED_NOT_CERTIFIED")
            self.assertEqual(len(digest), 64)
            self.assertNotIn("component:default", str(obj))
            self.assertEqual(obj["summary"]["counts"]["albandrieu.com"], 5)
            self.assertIsInstance(encoded, str)

    def test_candidate_graph_never_reaches_postgres_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "private.json"
            item = self.amass()
            item["candidates"] = [{"hostname": "secret.example.com"}]
            p.write_text(json.dumps(item))
            with self.assertRaises(ValueError):
                STORE["validate_receipt"]("amass", p)

    def test_invalid_mode_never_persisted(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "passive.json"
            item = self.amass()
            item["scan_mode"] = "passive"
            p.write_text(json.dumps(item))
            with self.assertRaises(ValueError):
                STORE["validate_receipt"]("amass", p)

    def test_checkdmarc_receipt_uses_only_sanitized_report(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "mail.json"
            p.write_text(json.dumps(self.mail()))
            obj, digest, _ = STORE["validate_receipt"]("checkdmarc", p)
            self.assertEqual(obj["summary"]["domainCount"], len(OWNED))
            self.assertEqual(obj["scanner"], "checkdmarc")
            self.assertEqual(len(digest), 64)
            item = self.mail()
            item["checkdmarc"]["results"][0]["raw_spf"] = "v=spf1 include:secret"
            p.write_text(json.dumps(item))
            with self.assertRaises(ValueError):
                STORE["validate_receipt"]("checkdmarc", p)

    def test_reviewed_mail_findings_pass_explicit_dojo_allowlist(self):
        domains = APPROVED
        result = PROJECT["project"](
            self.mail(), domains, now=datetime(2026, 11, 21, 2, tzinfo=timezone.utc)
        )
        self.assertEqual(len(result["findings"]), 2)
        self.assertEqual({x["severity"] for x in result["findings"]}, {"Medium"})
        VALIDATE["validate"](
            "ctem-mail", "Generic Findings Import", json.dumps(result).encode()
        )
        with self.assertRaises(ValueError):
            VALIDATE["validate"](
                "nabla-compose", "Generic Findings Import", json.dumps(result).encode()
            )
        result["findings"][0]["description"] += " extra cookie"
        with self.assertRaises(ValueError):
            VALIDATE["validate"](
                "ctem-mail", "Generic Findings Import", json.dumps(result).encode()
            )

    def test_stale_or_incomplete_mail_never_promoted(self):
        item = self.mail()
        item["checkdmarc"]["status"] = "INCOMPLETE"
        with self.assertRaises(ValueError):
            PROJECT["project"](
                item, APPROVED,
                now=datetime(2026, 11, 21, 2, tzinfo=timezone.utc),
            )
        item["checkdmarc"]["status"] = "OBSERVED_NOT_CERTIFIED"
        with self.assertRaises(ValueError):
            PROJECT["project"](
                item, set(item["scope"]),
                now=datetime(2026, 12, 21, tzinfo=timezone.utc),
            )

    def test_dedup_id_stable(self):
        domains = APPROVED
        clock = datetime(2026, 11, 21, 2, tzinfo=timezone.utc)
        one = PROJECT["project"](self.mail(), domains, now=clock)
        two = PROJECT["project"](self.mail(), domains, now=clock)
        self.assertEqual(one, two)


if __name__ == "__main__":
    unittest.main()
