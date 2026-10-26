"""Offline contracts: safe structured Doctor lint for failed OpenClaw Gateway."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SOURCE = (Path(__file__).resolve().parents[1]
          / "scripts/workstation/diagnose-openclaw-gateway-doctor-lint.py")
spec = importlib.util.spec_from_file_location("oc_gateway_doctor_lint", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class GatewayDoctorLintContracts(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        node = root / "node"
        entry = root / "openclaw.mjs"
        node.write_bytes(b"test")
        entry.write_bytes(b"test")
        node.chmod(0o700)
        entry.chmod(0o600)
        self.node = node
        self.entry = entry
        binding = patch.object(mod, "installation", return_value=(node, entry))
        binding.start()
        self.addCleanup(binding.stop)

    def test_json_with_raw_preamble_is_parsed_but_not_exposed(self):
        source = (b"PRIVATE token sk-NEVER-SHOW\n"
                  + json.dumps({"schemaVersion": 1, "ok": False, "checksRun": 2,
                                 "findings": [{"checkId": "core/doctor/gateway-config",
                                               "path": "gateway.mode",
                                               "severity": "warning",
                                               "message": "secret=sk-NEVER-SHOW"}]}).encode())
        self.assertEqual(mod.extract_json(source)["schemaVersion"], 1)
        with patch.object(mod.subprocess, "run",
                          return_value=SimpleNamespace(returncode=1,
                                                       stdout=source,
                                                       stderr=b"private key")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.run_doctor(), 0)
        text = output.getvalue()
        self.assertIn("doctor_diagnosis=gateway_config", text)
        self.assertIn("doctor_gateway_config_findings=1", text)
        self.assertIn("doctor_ok=no", text)
        self.assertIn("doctor_repairs_performed=false", text)
        self.assertNotIn("NEVER-SHOW", text)
        self.assertNotIn("PRIVATE", text)

    def test_schema_and_plugin_categories(self):
        checks = [
            ("core/doctor/state-schema-migration", "schema_migration"),
            ("plugin/doctor/plugin-compatibility", "plugin"),
            ("core/doctor/auth-profiles", "auth"),
            ("core/doctor/session-snapshots", "session_storage"),
            ("core/doctor/unknown", "other_findings"),
        ]
        for check, expected in checks:
            with self.subTest(check=check):
                report = {"findings": [{"checkId": check, "severity": "error"}]}
                self.assertEqual(mod.issue_category(report), expected)

    def test_lint_is_readonly_pinned_and_does_not_run_model(self):
        calls = []
        report = json.dumps({"schemaVersion": 1, "ok": True,
                             "checksRun": 7, "findings": []}).encode()
        def subprocess_mock(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return SimpleNamespace(returncode=0, stdout=report, stderr=b"")
        with patch.object(mod.subprocess, "run", side_effect=subprocess_mock), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.run_doctor(), 0)
        cmd, kwargs = calls[0]
        self.assertEqual(cmd, [str(self.node), str(self.entry),
                               "doctor", "--lint", "--json"])
        for forbidden in ("--fix", "--repair", "--yes", "update", "gateway",
                          "smoke", "--allow-exec"):
            self.assertNotIn(forbidden, cmd)
        self.assertEqual(kwargs["check"], False)
        self.assertIn("doctor_diagnosis=no_reported_findings", output.getvalue())

    def test_no_unsafe_binary_or_cli(self):
        self.entry.unlink()
        self.entry.symlink_to(self.node)
        with patch.object(mod.subprocess, "run") as process, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.run_doctor(), 2)
        self.assertIn("doctor_runtime=unverified", output.getvalue())
        process.assert_not_called()

    def test_bad_json_and_nonzero_code_does_not_claim_success(self):
        with patch.object(mod.subprocess, "run",
                          return_value=SimpleNamespace(returncode=2, stdout=b"FAIL PRIVATE",
                                                       stderr=b"secret")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.run_doctor(), 2)
        self.assertIn("doctor_diagnosis=report_unavailable", output.getvalue())
        self.assertNotIn("PRIVATE", output.getvalue())

    def test_lint_missing_fields_not_healthy(self):
        parsed = {"schemaVersion": 1, "findings": [], "checksRun": 0,
                  "ok": False}
        with patch.object(mod.subprocess, "run",
                          return_value=SimpleNamespace(returncode=2,
                                                       stdout=json.dumps(parsed).encode(),
                                                       stderr=b"")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.run_doctor(), 0)
        self.assertIn("doctor_ok=no", output.getvalue())
        self.assertIn("doctor_checks_run=0", output.getvalue())

    def test_output_categories_do_not_trust_arbitrary_field_paths(self):
        findings = [{"checkId": "PRIVATE",
                     "path": "/home/SECRET/.openclaw",
                     "severity": "warning",
                     "message": "sk-PRIVATE"}]
        report = {"schemaVersion": 1, "checksRun": 2, "ok": False, "findings": findings}
        with patch.object(mod.subprocess, "run",
                          return_value=SimpleNamespace(returncode=1,
                                                       stdout=json.dumps(report).encode(),
                                                       stderr=b"")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.run_doctor(), 0)
        self.assertNotIn("PRIVATE", output.getvalue())
        self.assertNotIn("SECRET", output.getvalue())


if __name__ == "__main__":
    unittest.main()
