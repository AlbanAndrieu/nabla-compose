"""Offline security contracts for read-only OpenClaw failed-service triage."""
import contextlib
import importlib.util
import io
import os
import stat
import tempfile
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
            ("newer database schema version encountered", "newer_database_schema"),
            ("newer schema version cannot be loaded", "newer_database_schema"),
            ("Offline schema migration is required", "offline_state_migration_required"),
            ("config was written by version 2026.10.7", "newer_written_config"),
            ("Invalid gateway config; refusing startup", "invalid_configuration"),
            ("some unrelated PRIVATE prompt", "no_known_pattern"),
        )
        for msg, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(mod.classify_journal([msg]), expected)

    def test_mise_node_patch_upgrade_is_not_falsely_marked_drift(self):
        from unittest.mock import patch
        for version in ("24.22.1", "24.22.2", "24.23.0"):
            with self.subTest(version=version):
                directory = f"/home/operator/.local/share/mise/installs/node/{version}"
                unit = (
                    f"{{ path={directory}/bin/node ; "
                    f"argv[]={directory}/bin/node "
                    f"{directory}/lib/node_modules/openclaw/openclaw.mjs "
                    "gateway --port 18789 }}"
                )
                with patch.object(mod, "run", return_value=(0, unit.encode())):
                    self.assertEqual(
                        mod.current_unit_matches_expected(),
                        "target_binding_confirmed",
                    )

    def test_mise_node_mismatched_versions_stay_unverified(self):
        root = "/home/operator/.local/share/mise/installs/node"
        binary = root + "/24.22.2/bin/node"
        module = root + "/24.22.1/lib/node_modules/openclaw/openclaw.mjs"
        with patch.object(
            mod, "run", return_value=(0, (binary + " " + module +
                                               " gateway --port 18789").encode()),
        ):
            self.assertEqual(mod.current_unit_matches_expected(),
                             "different_or_unverified")

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
             patch.object(mod, "journal_sample", return_value=(journal, "recent_30m")), \
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
             patch.object(mod, "journal_sample", return_value=(None, "no_user_journal")), \
             patch.object(mod, "file_log_sample", return_value=(None, "no_safe_file_logs")), \
             patch.object(mod, "current_unit_matches_expected",
                          return_value="unverified"), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(), 2)
        self.assertIn("service_properties=unavailable", output.getvalue())

    def test_30min_journal_falls_back_to_historical_tail(self):
        commands = []
        def response(argv, timeout=8):
            commands.append(argv)
            if "--since" in argv:
                return 0, b""
            return 0, b"Refusing newer database schema for agent sk-PRIVATE"
        with patch.object(mod, "run", side_effect=response):
            lines, source = mod.journal_sample()
        self.assertEqual(source, "historic_tail")
        self.assertEqual(mod.classify_journal(lines), "newer_database_schema")
        self.assertTrue(any("--lines" in cmd and "--since" not in cmd for cmd in commands))

    def test_exit78_without_any_logs_remains_unattributed(self):
        props = {"ActiveState": "failed", "SubState": "failed",
                 "Result": "exit-code", "ExecMainStatus": "78",
                 "NRestarts": "0"}
        with patch.object(mod, "systemd_properties", return_value=props), \
             patch.object(mod, "journal_sample",
                          return_value=(None, "no_user_journal")), \
             patch.object(mod, "file_log_sample",
                          return_value=(None, "no_safe_file_logs")), \
             patch.object(mod, "current_unit_matches_expected",
                          return_value="target_binding_confirmed"), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(), 0)
        self.assertIn("exit_78_interpretation=config_or_schema_unattributed",
                      output.getvalue())
        self.assertIn("journal_lines_inspected=0", output.getvalue())

    def test_file_log_sample_is_bounded_and_owner_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            folder.chmod(0o700)
            file = folder / "openclaw-2026-10-26.log"
            file.write_text("private key sk-NEVER-SHARE\nnewer database schema")
            file.chmod(0o600)
            constructor = (lambda value: folder if value == "/tmp/openclaw" else
                           folder / "absent-scoped-dir" if value == "/tmp" else Path(value))
            with patch.object(mod, "Path", side_effect=constructor), \
                 patch.object(mod.time, "time", return_value=file.stat().st_mtime):
                lines, source = mod.file_log_sample()
            self.assertEqual(source, "private_file_tail")
            self.assertEqual(mod.classify_journal(lines), "newer_database_schema")

    def test_file_log_refuses_symlink_or_group_writable_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            folder.chmod(0o700)
            secret = folder / "private"
            secret.write_text("newer database schema")
            candidate = folder / "openclaw-2026-10-26.log"
            candidate.symlink_to(secret)
            constructor = (lambda value: folder if value == "/tmp/openclaw" else
                           folder / "absent-scoped-dir" if value == "/tmp" else Path(value))
            with patch.object(mod, "Path", side_effect=constructor):
                lines, source = mod.file_log_sample()
            self.assertIsNone(lines)
            self.assertEqual(source, "no_safe_file_logs")
            candidate.unlink()
            candidate.write_text("newer database schema")
            candidate.chmod(0o666)
            with patch.object(mod, "Path", side_effect=constructor):
                lines, source = mod.file_log_sample()
            self.assertIsNone(lines)


    def test_journal_patterns_do_not_reveal_private_tokens(self):
        props = {"ActiveState": "failed", "SubState": "failed",
                 "Result": "exit-code", "ExecMainStatus": "78",
                 "NRestarts": "0"}
        lines = ["token sk-PRIVATE", "newer database schema from /home/PRIVATE"]
        with patch.object(mod, "systemd_properties", return_value=props), \
             patch.object(mod, "journal_sample",
                          return_value=(lines, "historic_tail")), \
             patch.object(mod, "current_unit_matches_expected",
                          return_value="target_binding_confirmed"), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(), 0)
        self.assertIn("journal_pattern=newer_database_schema", output.getvalue())
        self.assertIn("journal_source=historic_tail", output.getvalue())
        self.assertIn("exit_78_interpretation=classified", output.getvalue())
        self.assertNotIn("PRIVATE", output.getvalue())

    def test_unclassified_240_journal_lines_use_private_file_log_evidence(self):
        props = {"ActiveState": "failed", "SubState": "failed",
                 "Result": "exit-code", "ExecMainStatus": "78",
                 "NRestarts": "0"}
        journal = ["irrelevant log with sk-PRIVATE"] * 240
        file_lines = ["Config validation failed: sk-SECRET /home/operator"]
        with patch.object(mod, "systemd_properties", return_value=props), \
             patch.object(mod, "journal_sample",
                          return_value=(journal, "historic_tail")), \
             patch.object(mod, "file_log_sample",
                          return_value=(file_lines, "private_file_tail")) as fallback, \
             patch.object(mod, "current_unit_matches_expected",
                          return_value="target_binding_confirmed"), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(), 0)
        fallback.assert_called_once()
        result = output.getvalue()
        self.assertIn("journal_source=private_file_tail", result)
        self.assertIn("file_log_fallback=private_file_tail", result)
        self.assertIn("journal_pattern=invalid_configuration", result)
        self.assertIn("exit_78_interpretation=classified", result)
        self.assertNotIn("SECRET", result)
        self.assertNotIn("PRIVATE", result)
        self.assertNotIn("/home/operator", result)

    def test_known_journal_fatal_does_not_consult_file_logs(self):
        props = {"ActiveState": "failed", "Result": "exit-code",
                 "ExecMainStatus": "78"}
        with patch.object(mod, "systemd_properties", return_value=props), \
             patch.object(mod, "journal_sample", return_value=(
                 ["state database is busy, token=SECRET"], "historic_tail")), \
             patch.object(mod, "file_log_sample") as fallback, \
             patch.object(mod, "current_unit_matches_expected",
                          return_value="target_binding_confirmed"), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(), 0)
        fallback.assert_not_called()
        self.assertIn("journal_pattern=state_owner_contention", output.getvalue())
        self.assertIn("file_log_fallback=not_needed", output.getvalue())
        self.assertNotIn("SECRET", output.getvalue())

    def test_unmatched_file_log_does_not_claim_exit78_attribution(self):
        props = {"ActiveState": "failed", "Result": "exit-code",
                 "ExecMainStatus": "78"}
        with patch.object(mod, "systemd_properties", return_value=props), \
             patch.object(mod, "journal_sample",
                          return_value=(["unrelated supervisor chatter"], "historic_tail")), \
             patch.object(mod, "file_log_sample",
                          return_value=(["another irrelevant record"], "private_file_tail")), \
             patch.object(mod, "current_unit_matches_expected",
                          return_value="target_binding_confirmed"), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(), 0)
        self.assertIn("journal_source=historic_tail", output.getvalue())
        self.assertIn("file_log_fallback=private_file_tail", output.getvalue())
        self.assertIn("exit_78_interpretation=config_or_schema_unattributed",
                      output.getvalue())

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
