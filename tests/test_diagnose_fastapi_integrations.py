"""Offline contract checks for the read-only TrueNAS reboot diagnostic."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import json


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/truenas/diagnose-fastapi-integrations.py"
SPEC = importlib.util.spec_from_file_location("diagnose_fastapi_integrations", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


class RebootDiagnosticTests(TestCase):
    def test_tcp_failure_is_classified_without_secret_or_host_leak(self):
        with mock.patch.object(diagnostic.socket, "create_connection", side_effect=OSError("private detail")):
            result = diagnostic.check_tcp("127.0.0.1", 5432, 0.2)
        self.assertEqual(result["state"], "unreachable")
        self.assertEqual(result["error_type"], "OSError")
        self.assertNotIn("private detail", json.dumps(result))

    def test_missing_application_script_does_not_break_host_diagnosis(self):
        with TemporaryDirectory() as tempdir:
            result = diagnostic.diagnose_fastapi(
                Path(tempdir) / "nonexistent.py", "http://127.0.0.1:8091", 1.0
            )
        self.assertEqual(result["reason"], "diagnostic_script_missing")

    def test_invalid_application_json_is_reported_not_executed_again(self):
        with TemporaryDirectory() as tempdir:
            script = Path(tempdir) / "stub.py"
            script.write_text("print('invalid json')\n", encoding="utf-8")
            result = diagnostic.diagnose_fastapi(script, "http://127.0.0.1:8091", 2.0)
        self.assertEqual(result["state"], "unavailable")
        self.assertEqual(result["reason"], "invalid_diagnostic_json")

    def test_application_partial_evidence_does_not_become_green(self):
        with TemporaryDirectory() as tempdir:
            script = Path(tempdir) / "stub.py"
            script.write_text(
                "import json, sys\n"
                "print(json.dumps({'evidence_complete': False, 'evidence_gaps': ['sentry'], "
                "'dependencies': {'redis': {'operational_state': 'ok', 'evidence_complete': True}}}))\n"
                "sys.exit(1)\n",
                encoding="utf-8",
            )
            result = diagnostic.diagnose_fastapi(script, "http://127.0.0.1:8091", 2.0)
        self.assertEqual(result["state"], "incomplete")
        self.assertEqual(result["evidence_gaps"], ["sentry"])
