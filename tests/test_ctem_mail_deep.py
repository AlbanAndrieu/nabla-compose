"""Independent DNS evidence projection, no network."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "mail_deep", ROOT / "scripts/security/run-public-mail-deep.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MailDeepContract(unittest.TestCase):
    def test_checkdmarc_projection_keeps_only_approved_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "mail.json"
            raw.write_text(json.dumps([{"domain": "bababou.com",
                                       "spf": {"valid": True, "dns_lookups": 2, "record": "secret"},
                                       "dmarc": {"valid": True, "tags": {"p": {"value": "reject"}}}}]))
            projected = MODULE.project_checkdmarc(raw, {"bababou.com"})
            self.assertEqual(projected[0]["dmarc_p"], "reject")
            self.assertNotIn("secret", json.dumps(projected))
            with self.assertRaises(ValueError):
                MODULE.project_checkdmarc(raw, {"albandrieu.com", "bababou.com"})

    def test_nuclei_projection_drops_txt_and_rejects_out_of_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "dns.jsonl"
            raw.write_text(json.dumps({"host": "bababou.com", "template-id": "dmarc-detect",
                                       "info": {"severity": "info"}, "extracted-results": ["secret"]}) + "\n")
            projected = MODULE.project_nuclei(raw, {"bababou.com": "bababou.com"}, {"dmarc-detect"})
            self.assertEqual(projected, [{"domain": "bababou.com", "template_id": "dmarc-detect",
                                          "severity": "info"}])
            with self.assertRaises(ValueError):
                MODULE.project_nuclei(raw, {"albandrieu.com": "albandrieu.com"}, {"dmarc-detect"})

    def test_missing_selectors_and_unavailable_tools_never_prove_success(self):
        rows = [{"name": "bababou.com", "mail_use": "unverified", "dkim_selectors": []}]
        with patch.object(MODULE, "execute", return_value=False):
            report = MODULE.audit(rows, Path("checkdmarc"), Path("nuclei"), Path("templates"))
        self.assertEqual(report["result"], "INCOMPLETE")
        self.assertEqual(report["nuclei_dkim"]["status"], "NOT_RUN_NO_SELECTORS")


if __name__ == "__main__":
    unittest.main()
