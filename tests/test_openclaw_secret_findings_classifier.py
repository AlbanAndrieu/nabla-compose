"""Synthetic-only tests for privacy-preserving OpenClaw finding classification."""
import importlib.util
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[1] / "scripts/workstation/classify-openclaw-secret-findings.py"
spec = importlib.util.spec_from_file_location("finding_classifier", SRC)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ClassificationTests(unittest.TestCase):
    def test_locations_without_value_leakage(self):
        root = module.ROOT
        report = {"findings": [
            {"path": str(root / "openclaw.json"), "secret": "sk-private"},
            {"file": str(root / ".env"), "token": "private"},
            {"path": "/other/private/service.json", "id": "sensitive"},
            {"value": "private"},
        ]}
        counts = module.classify(report)
        self.assertEqual(dict(counts), {
            "openclaw_json": 1, "dotenv": 1, "other_file": 1,
            "unclassified": 1,
        })
        self.assertNotIn("private", str(counts))
        self.assertNotIn("sensitive", str(counts))

    def test_unsupported_report_fails_closed(self):
        with self.assertRaises(ValueError):
            module.classify({"findings": "untrusted"})
        with self.assertRaises(ValueError):
            module.classify(None)


if __name__ == "__main__":
    unittest.main()
