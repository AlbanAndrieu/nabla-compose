"""Offline TLS evidence privacy and failure semantics."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ctem_tls", ROOT / "scripts/security/run-public-tls-audit.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CtemTlsAuditTest(unittest.TestCase):
    def test_projection_never_emits_raw_finding(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "raw.json"
            path.write_text(json.dumps([{"id": "TLS1_2", "severity": "OK",
                                         "finding": "private certificate detail"}]))
            self.assertEqual(MODULE.project_report(path),
                             [{"id": "TLS1_2", "severity": "OK"}])

    def test_empty_and_invalid_reports_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "raw.json"
            for content in ("[]", "{}", '[{"id":"../secret","severity":"HIGH"}]'):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    MODULE.project_report(path)

    def test_timeout_is_not_zero_findings(self):
        with patch.object(MODULE.subprocess, "run",
                          side_effect=MODULE.subprocess.TimeoutExpired("testssl", 1)):
            report = MODULE.audit(Path("testssl.sh"))
            self.assertEqual(report["result"], "INCOMPLETE")
            self.assertTrue(all(row["status"] == "INCOMPLETE"
                                for row in report["results"]))


if __name__ == "__main__":
    unittest.main()
