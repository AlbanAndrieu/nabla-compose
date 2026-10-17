"""Offline contract tests for redacted OpenClaw secret audit summaries."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/check-openclaw-litellm-memory-config.py"
spec = importlib.util.spec_from_file_location("openclaw_memory_preflight", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AuditSummaryTests(unittest.TestCase):
    def test_known_categories(self):
        result = module.audit_summary({
            "plaintextSecrets": [{"secret": "never-display"}],
            "unresolvedRefs": [{"path": "/private"}],
            "precedenceDrift": [],
        })
        self.assertEqual(result["categories"], {
            "plaintext": 1, "unresolved": 1, "precedence_drift": 0,
        })
        self.assertNotIn("never-display", str(result))
        self.assertNotIn("/private", str(result))

    def test_unknown_schema_is_fail_closed(self):
        result = module.audit_summary({"findings": [{"token": "sensitive"}]})
        self.assertEqual(result["schema"], "unknown")
        self.assertTrue(result["unclassified"])
        self.assertNotIn("sensitive", str(result))

    def test_invalid_or_boolean_counts_not_accepted(self):
        result = module.audit_summary({"plaintext": True})
        self.assertEqual(result["schema"], "unknown")


if __name__ == "__main__":
    unittest.main()
