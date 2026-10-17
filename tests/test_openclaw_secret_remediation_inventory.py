"""Synthetic secret-remediation inventory tests."""
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/workstation/audit-openclaw-secret-remediation.py"
spec = importlib.util.spec_from_file_location("secret_cross_tab", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class AuditCrossTabTests(unittest.TestCase):
    def test_cross_tab_never_contains_secret_values(self):
        report = {
            "summary": {"plaintextCount": 2, "legacyResidueCount": 1},
            "findings": [
                {"path": str(mod.HOME / ".openclaw/openclaw.json"), "type": "plaintext", "value": "sk-sensitive"},
                {"file": str(mod.HOME / ".openclaw/.env"), "type": "legacy-residue", "value": "private"},
                {"path": "/private/other", "type": "unrecognized", "value": "secret"},
            ],
        }
        counts = mod.summarize(report)
        self.assertEqual(counts[("config", "plaintext")], 1)
        self.assertEqual(counts[("dotenv", "legacy")], 1)
        self.assertEqual(counts[("other", "unknown")], 1)
        self.assertNotIn("sensitive", str(counts))
        self.assertNotIn("/private", str(counts))

    def test_mismatch_fails_closed(self):
        with self.assertRaises(ValueError):
            mod.summarize({"summary": {"plaintextCount": 3, "legacyResidueCount": 0},
                           "findings": [{"path": "openclaw.json"}]})


if __name__ == "__main__":
    unittest.main()
