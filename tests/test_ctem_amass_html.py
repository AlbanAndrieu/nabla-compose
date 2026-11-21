"""Private, safe, offline CTEM HTML visualization contracts."""
from pathlib import Path
import runpy
import tempfile
import unittest

MOD = runpy.run_path(
    str(Path(__file__).resolve().parents[1] /
        "scripts/security/render-ctem-amass-html.py")
)
REVISION = "sha256:" + "a" * 64


def examples():
    catalog = {
        "catalogRevision": REVISION,
        "status": "OBSERVED_NOT_CERTIFIED",
    }
    public = {
        "schema_version": 1,
        "scanner": "amass",
        "scanner_version": "5.1.3",
        "scan_mode": "active",
        "checked_at": "2026-11-21T10:00:00+00:00",
        "status": "OBSERVED_NOT_CERTIFIED",
        "vantage": "truenas-internal",
        "counts": {"example.com": 1},
        "catalogReconciliation": catalog,
    }
    private = {
        **public,
        "candidates": [{
            "hostname": "portal.example.com",
            "domain": "example.com",
            "catalogMatch": "MATCHED_PUBLIC_INTENT",
            "catalogMatches": [{
                "entityRef": "component:default/example",
            }],
        }],
    }
    return public, private


class PrivateAmassHTMLTests(unittest.TestCase):
    def test_safe_local_html_has_no_remote_imports(self):
        summary, private = examples()
        rendered = MOD["page"](summary, private)
        self.assertIn("portal.example.com", rendered)
        self.assertIn("component:default/example", rendered)
        self.assertIn("default-src 'none'", rendered)
        self.assertNotIn("cdn.jsdelivr.net", rendered)
        self.assertNotIn("<script", rendered)

    def test_escapes_reflected_name_and_mapping(self):
        summary, private = examples()
        private["candidates"][0]["catalogMatches"][0]["entityRef"] = "<script>alert(1)</script>"
        page = MOD["page"](summary, private)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>alert(1)</script>", page)

    def test_invalid_status_or_revision_rejected(self):
        summary, private = examples()
        summary["status"] = "INCOMPLETE"
        private["status"] = "INCOMPLETE"
        with self.assertRaises(ValueError):
            MOD["page"](summary, private)
        summary, private = examples()
        summary["catalogReconciliation"]["catalogRevision"] = "not_sha256"
        with self.assertRaises(ValueError):
            MOD["page"](summary, private)

    def test_private_candidate_outside_domain_rejected(self):
        summary, private = examples()
        private["candidates"][0]["hostname"] = "portal.example.com.evil.test"
        with self.assertRaises(ValueError):
            MOD["page"](summary, private)

    def test_candidate_mismatch_and_duplicate_rejected(self):
        summary, private = examples()
        private["candidates"].append(private["candidates"][0].copy())
        with self.assertRaises(ValueError):
            MOD["page"](summary, private)

    def test_read_requires_owner_private_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "report.json"
            p.write_text("{}")
            p.chmod(0o644)
            with self.assertRaises(ValueError):
                MOD["private_json"](p)
            p.chmod(0o600)
            self.assertEqual(MOD["private_json"](p), {})


if __name__ == "__main__":
    unittest.main()
