"""Read-only session lookup contract for OpenClaw cron agent."""
import importlib.util
import json
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[1] / "scripts/workstation/diagnose-openclaw-cron-parent.py"
spec = importlib.util.spec_from_file_location("cron_parent", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CronParentTests(unittest.TestCase):
    def test_detects_present_main_reference_without_printing_keys(self):
        report = mod.classify(json.dumps({
            "sessions": [{"key": "agent:cron:main"},
                         {"key": "agent:cron:secret-uuid-PRIVATE"}],
            "hasMore": False}).encode())
        self.assertEqual(report["cron_main_reference"], "present")
        self.assertEqual(report["session_sample_count"], 2)
        self.assertIs(report["session_sample_exhaustive"], True)
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_absence_in_paginated_sample_is_not_global_absence(self):
        report = mod.classify(json.dumps({
            "sessions": [{"key": "agent:cron:job-123"}],
            "hasMore": True}).encode())
        self.assertEqual(report["cron_main_reference"], "absent_in_bounded_sample")
        self.assertIs(report["session_sample_exhaustive"], False)

    def test_unknown_schema_refuses_negative_claim(self):
        report = mod.classify(json.dumps({"data": []}).encode())
        self.assertEqual(report["cron_main_reference"], "unverified")
        self.assertEqual(mod.classify(b"{bad")["cron_session_catalog"], "unverified")

    def test_oversize_and_non_string_keys_refused(self):
        self.assertEqual(mod.classify(b" " * (mod.MAX_BYTES + 1))["cron_session_catalog"],
                         "unverified")
        self.assertEqual(mod.classify(json.dumps({"sessions": [{"key": None}]}).encode())
                         ["cron_session_catalog"], "unverified")

if __name__ == "__main__":
    unittest.main()
