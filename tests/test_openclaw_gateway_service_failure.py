"""Offline security contracts for read-only OpenClaw failed-service triage."""
import contextlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch

SOURCE = (Path(__file__).resolve().parents[1]
          / "scripts/workstation/diagnose-openclaw-gateway-service-failure.py")
spec = importlib.util.spec_from_file_location("oc_service_failure", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class OpenClawServiceFailureTests(unittest.TestCase):
    def test_exact_failure_classification(self):
        cases = (
            ("GatewayStateOwnerContentionError: state database is busy", "state_owner_contention"),
            ("[state/db] schema migration failed", "state_migration"),
            ("Error: EBADENGINE", "node_runtime"),
            ("listen EADDRINUSE 0.0.0.0", "port_conflict"),
            ("Error [ERR_MODULE_NOT_FOUND] missing", "missing_dependency"),
            ("EACCES: permission denied", "filesystem_permission"),
            ("config failed validation", "configuration"),
            ("plugin reload failed", "plugin_initialization"),
            ("SecretRef unavailable", "authentication"),
            ("JavaScript heap out of memory", "out_of_memory"),
            ("some unrelated PRIVATE prompt", "no_known_pattern"),
        )
        for msg, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(mod.classify_journal([msg]), expected)

    def test_missing_journal_is_not_called_healthy(self):
        self.assertEqual(mod.classify_journal(None), "journal_unavailable")
        self.assertEqual(mod.classify_journal([]), "no_recent_journal_evidence")

    def test_output_is_redacted(self):
        properties = {"ActiveState": "failed", "SubState": "failed",
                      "Result": "exit-code", "ExecMainStatus": "1",
                      "NRestarts": "5"}
        journal = ["secret_key=sk-PRIVATE", "Error: ERR_MODULE_NOT_FOUND",
                   "/home/user/.openclaw/openclaw.json"]
        with patch.object(mod, "systemd_properties", return_value=properties), \
             patch.object(mod, "journal_sample", return_value=journal), \
             patch.object(mod, "current_unit_matches_expected",
                          return_value="target_binding_confirmed"), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(), 0)
        result = output.getvalue()
        self.assertIn("service_state=failed", result)
        self.assertIn("service_exit_status=1", result)
        self.assertIn("journal_pattern=missing_dependency", result)
        self.assertIn("raw_journal_or_environment_printed=false", result)
        for forbidden in ("PRIVATE", "sk-", "/home", "openclaw.json"):
            self.assertNotIn(forbidden, result)

    def test_unrecognized_systemd_values_are_sanitized(self):
        self.assertEqual(mod.safe_enum("PRIVATE", mod.SAFE_RESULT), "unknown")
        self.assertEqual(mod.safe_number("-1"), "unknown")
        self.assertEqual(mod.safe_number("1111111111111"), "unknown")
        self.assertEqual(mod.safe_number("123"), "123")

    def test_subprocess_arguments_are_fixed_and_read_only(self):
        calls = []
        def fake_run(command, timeout=8):
            calls.append(command)
            if command[:3] == ["systemctl", "--user", "show"]:
                return 0, b"ActiveState=failed\nResult=exit-code\nExecMainStatus=1\n"
            return 0, b"Error: EADDRINUSE\nsk-PRIVATE"
        with patch.object(mod, "run", side_effect=fake_run), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(), 0)
        self.assertTrue(any(args[0] == "journalctl" for args in calls))
        for args in calls:
            self.assertNotIn("stop", args)
            self.assertNotIn("restart", args)
            self.assertNotIn("start", args)
            self.assertNotIn("sudo", args)
        self.assertNotIn("sk-PRIVATE", output.getvalue())

    def test_failing_systemctl_stays_unknown(self):
        with patch.object(mod, "systemd_properties", return_value=None), \
             patch.object(mod, "journal_sample", return_value=None), \
             patch.object(mod, "current_unit_matches_expected",
                          return_value="unverified"), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(), 2)
        self.assertIn("service_properties=unavailable", output.getvalue())

    def test_unit_binding_is_verified_but_never_printed(self):
        root = "/home/fixture"
        body = (f"path={root}/.local/share/mise/installs/node/24.22.1/bin/node "
                f"argv[]={root}/.local/share/mise/installs/node/24.22.1/"
                "lib/node_modules/openclaw/openclaw.mjs gateway --port 18789")
        with patch.object(mod, "run", return_value=(0, body.encode())):
            self.assertEqual(mod.current_unit_matches_expected(),
                             "target_binding_confirmed")
        with patch.object(mod, "run", return_value=(0, b"/usr/bin/node")):
            self.assertEqual(mod.current_unit_matches_expected(),
                             "different_or_unverified")


if __name__ == "__main__":
    unittest.main()
