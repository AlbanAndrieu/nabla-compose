"""Hermetic dual-mode diagnostics; no live Docker, SSH or billing."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/quality/agent-diagnostics.py"
SPEC = importlib.util.spec_from_file_location("agent_diagnostics", SCRIPT)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class AgentDiagnosticModes(unittest.TestCase):
    def test_default_remote_is_plan_only(self):
        with patch.object(MOD.subprocess, "run") as run, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(MOD.main([]), 0)
        run.assert_not_called()
        record = json.loads(output.getvalue())
        self.assertEqual(record["mode"], "remote")
        self.assertEqual(record["status"], "PLAN_ONLY")
        self.assertFalse(record["executed"])
        self.assertTrue(all(s["status"] == "NOT_RUN" for s in record["steps"]))

    def test_remote_cannot_enable_runtime_even_as_plan(self):
        with patch.object(MOD.subprocess, "run") as run, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(MOD.main([
                "--mode", "remote", "--scope", "openclaw",
                "--runtime-readonly", "--execute",
            ]), 2)
        run.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["status"], "BLOCKED_MODE")

    def test_workstation_runtime_is_explicit_not_automatic(self):
        base = MOD.planned("openclaw", "workstation", False)
        self.assertTrue(all(x["type"] == "offline" for x in base))
        extended = MOD.planned("openclaw", "workstation", True)
        self.assertEqual(len(extended), 2)
        self.assertEqual(extended[-1]["type"], "runtime_readonly")
        self.assertEqual(extended[-1]["argv"],
                         ["just", "openclaw-migration-evidence-check"])

    def test_runtime_requires_verified_local_user_gateway(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").touch()
            with patch.object(MOD, "workstation_runtime_ready", return_value=False), \
                 patch.object(MOD.subprocess, "run") as run, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                code = MOD.main([
                    "--mode", "workstation", "--scope", "openclaw",
                    "--runtime-readonly", "--execute", "--root", directory,
                ])
        self.assertEqual(code, 2)
        run.assert_not_called()
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "HOST_UNVERIFIED")
        self.assertFalse(report["executed"])

    def test_runtime_preflight_uses_systemd_and_is_fail_closed(self):
        with patch.object(MOD.sys, "platform", "linux"), \
             patch.dict(MOD.os.environ, {"CI": ""}), \
             patch.object(MOD.subprocess, "run",
                          return_value=SimpleNamespace(
                              returncode=0, stdout=b"loaded\n")) as run:
            self.assertTrue(MOD.workstation_runtime_ready())
        self.assertEqual(run.call_args.args[0][0:3],
                         ["systemctl", "--user", "show"])
        with patch.object(MOD.sys, "platform", "linux"), \
             patch.dict(MOD.os.environ, {"CI": "true"}), \
             patch.object(MOD.subprocess, "run") as run:
            self.assertFalse(MOD.workstation_runtime_ready())
            run.assert_not_called()

    def test_remote_executes_only_offline_tests_when_checkout_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("synthetic\n")
            (root / "tests").mkdir()
            (root / "tests/test_agent_skill_precedence_contract.py").touch()
            with patch.object(MOD.shutil, "which", return_value="/bin/python3"), \
                 patch.object(MOD.subprocess, "run",
                              return_value=SimpleNamespace(returncode=0)) as run, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                code = MOD.main([
                    "--mode", "remote", "--scope", "policy", "--execute",
                    "--root", directory,
                ])
            self.assertEqual(code, 0)
            self.assertEqual(run.call_count, 2)
            self.assertTrue(all(
                c.kwargs["stdout"] is MOD.subprocess.DEVNULL
                and c.kwargs["stderr"] is MOD.subprocess.DEVNULL
                for c in run.call_args_list
            ))
            report = json.loads(output.getvalue())
            self.assertEqual(report["status"], "PASS")
            self.assertFalse(report["runtime_allowed"])
            self.assertNotIn("synthetic", output.getvalue())

    def test_missing_checkout_blocks_execution(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(MOD.subprocess, "run") as run, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(MOD.main([
                "--mode", "workstation", "--execute", "--root", directory]), 2)
        run.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["status"], "NO_CHECKOUT")

    def test_failing_step_stops_next_expensive_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").touch()
            (root / "tests").mkdir()
            (root / "tests/test_agent_skill_precedence_contract.py").touch()
            with patch.object(MOD.shutil, "which", return_value="/bin/python"), \
                 patch.object(MOD.subprocess, "run",
                              return_value=SimpleNamespace(returncode=2)) as run, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                code = MOD.main([
                    "--mode", "workstation", "--scope", "policy", "--execute",
                    "--root", directory,
                ])
            self.assertEqual(code, 2)
            self.assertEqual(run.call_count, 1)
            report = json.loads(output.getvalue())
            self.assertEqual(report["status"], "UNVERIFIED")
            self.assertEqual(report["steps"][1]["status"], "NOT_RUN_AFTER_FAILURE")

    def test_offline_children_drop_secret_environment(self):
        with patch.dict(MOD.os.environ, {
            "BW_SESSION": "SYNTHETIC_SECRET_NEVER_PRINT",
            "LITELLM_MASTER_KEY": "SYNTHETIC_MASTER_NEVER_PRINT",
            "CUSTOM_TEST_VAR": "keep",
        }):
            stripped = MOD.safe_environment()
        self.assertNotIn("BW_SESSION", stripped)
        self.assertNotIn("LITELLM_MASTER_KEY", stripped)
        self.assertNotIn("CUSTOM_TEST_VAR", stripped)
        self.assertEqual(stripped["PYTHONDONTWRITEBYTECODE"], "1")

    def test_unknown_runtime_scope_is_denied(self):
        with self.assertRaises(ValueError):
            MOD.planned("secrets", "workstation", True)

    def test_missing_unittest_target_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").touch()
            with patch.object(MOD.shutil, "which", return_value="/bin/python3"), \
                 patch.object(MOD.subprocess, "run") as run, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                code = MOD.main(["--scope", "policy", "--execute",
                                 "--root", directory])
        self.assertEqual(code, 2)
        run.assert_called_once()
        report = json.loads(output.getvalue())
        self.assertEqual(report["steps"][1]["status"], "MISSING_TEST")

    def test_execution_never_invokes_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").touch()
            (root / "tests").mkdir()
            (root / "tests/test_agent_skill_precedence_contract.py").touch()
            with patch.object(MOD.shutil, "which", return_value="/bin/python3"), \
                 patch.object(MOD.subprocess, "run",
                              return_value=SimpleNamespace(returncode=0)) as run, \
                 contextlib.redirect_stdout(io.StringIO()):
                MOD.main(["--scope", "policy", "--execute", "--root", directory])
        for call in run.call_args_list:
            self.assertNotIn("shell", call.kwargs)
            self.assertIsInstance(call.args[0], list)


if __name__ == "__main__":
    unittest.main()
