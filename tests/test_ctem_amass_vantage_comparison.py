"""Offline acceptance of external Amass artifact and vantage comparison."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PULL = runpy.run_path(str(ROOT / "scripts/security/pull-ctem-amass-artifact.py"))
COMP = runpy.run_path(str(ROOT / "scripts/security/compare-ctem-amass-vantages.py"))
NOW = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)
SHA = "a" * 40
REV = "sha256:" + "b" * 64
DOMAINS = ["albanandrieu.com", "albandrieu.com", "bababou.com"]


def evidence(vantage="truenas-internal", counts=None, revision=REV, status="OBSERVED_NOT_CERTIFIED"):
    return {
        "schema_version": 1, "scanner": "amass", "scanner_version": "5.1.3",
        "scan_mode": "active", "status": status, "vantage": vantage,
        "source_revision": SHA, "checked_at": (NOW - timedelta(hours=2)).isoformat(),
        "scope": DOMAINS, "counts": counts or dict.fromkeys(DOMAINS, 3),
        "catalogReconciliation": {
            "status": "OBSERVED_NOT_CERTIFIED", "catalogRevision": revision,
        }
    }


def zip_report(payload, extra=False):
    buf = BytesIO()
    with ZipFile(buf, "w") as z:
        z.writestr("public-amass-summary.json", json.dumps(payload))
        if extra:
            z.writestr("candidate-names.json", "secret")
    return buf.getvalue()


class VantageTests(unittest.TestCase):
    def test_equal_counts_not_proof_of_equal_assets(self):
        result = COMP["compare"](evidence(),
            evidence("external-github-hosted"), now=NOW)
        self.assertEqual(result["status"], "SAME_COUNTS_NOT_SAME_ASSETS")
        self.assertNotIn("hostname", str(result))

    def test_difference_requires_review_not_down(self):
        outside = evidence("external-github-hosted",
                           {DOMAINS[0]: 9, DOMAINS[1]: 3, DOMAINS[2]: 3})
        result = COMP["compare"](evidence(), outside, now=NOW)
        self.assertEqual(result["status"], "COUNT_DIFFERENCE_REVIEW")
        self.assertEqual(result["rows"][0]["count_delta_external_minus_truenas"], 6)
        self.assertNotIn("DOWN", str(result))

    def test_reject_stale_and_different_catalog_revision(self):
        with self.assertRaisesRegex(ValueError, "revisions differ"):
            COMP["compare"](evidence(), evidence("external-github-hosted",
                          revision="sha256:" + "c"*64), now=NOW)
        old = evidence("external-github-hosted")
        old["checked_at"] = (NOW - timedelta(days=17)).isoformat()
        with self.assertRaises(ValueError):
            COMP["compare"](evidence(), old, now=NOW)

    def test_refuse_private_candidates_and_bad_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "candidate.json"
            doc = evidence()
            doc["candidates"] = [{"hostname": "secret.example.com"}]
            p.write_text(json.dumps(doc))
            p.chmod(0o600)
            with self.assertRaises(ValueError):
                COMP["private_report"](p)
        outside = evidence("external-github-hosted")
        outside["scope"] = ["not-mine.example"]
        with self.assertRaises(ValueError):
            COMP["compare"](evidence(), outside, now=NOW)

    def test_allow_only_successful_master_dispatch_run(self):
        record = {
            "id": 77, "name": "External attack surface (homelab)",
            "head_branch": "master", "event": "workflow_dispatch",
            "status": "completed", "conclusion": "success",
            "head_sha": SHA, "created_at": (NOW-timedelta(hours=1)).isoformat()
        }
        PULL["verify_run"](record, 77, now=NOW)
        for changed in (dict(record, event="pull_request"),
                        dict(record, conclusion="failure"),
                        dict(record, head_branch="feature")):
            with self.assertRaises(ValueError):
                PULL["verify_run"](changed, 77, now=NOW)

    def test_only_exact_counts_zip_with_provenance(self):
        report = evidence("external-github-hosted")
        self.assertEqual(json.loads(PULL["unpack"](zip_report(report), SHA)), report)
        with self.assertRaises(ValueError):
            PULL["unpack"](zip_report(report, extra=True), SHA)
        with self.assertRaises(ValueError):
            PULL["unpack"](zip_report({**report, "source_revision": "0"*40}), SHA)
        with self.assertRaises(ValueError):
            PULL["unpack"](zip_report({**report, "candidates": [{"hostname":"secret"}]}), SHA)

    def test_artifact_name_and_expiry(self):
        one = {"name": "public-amass-summary-77", "expired": False,
               "size_in_bytes": 200, "id": 900}
        self.assertEqual(PULL["verify_artifact"]([one], 77), 900)
        for artifacts in ([one, one], [{**one, "expired": True}],
                          [{**one, "name": "public-mail-deep-77"}]):
            with self.assertRaises(ValueError):
                PULL["verify_artifact"](artifacts, 77)

    def test_no_automatic_external_scans_or_database_connection(self):
        pull = (ROOT/"scripts/security/pull-ctem-amass-artifact.py").read_text()
        self.assertNotIn("docker run", pull)
        self.assertNotIn("psql", pull)
        self.assertNotIn("reimport-scan", pull)
        self.assertIn("CTEM_EXTERNAL_AMASS_PULL_APPROVED", pull)


if __name__ == "__main__":
    unittest.main()
