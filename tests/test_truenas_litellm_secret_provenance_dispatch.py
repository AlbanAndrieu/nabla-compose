"""Hermetic coverage for read-only secret provenance on TrueNAS and Workstation."""

from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/check-truenas-litellm-secret-provenance.py"
spec = importlib.util.spec_from_file_location("secret_provenance", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProvenanceDispatchTests(unittest.TestCase):
    def test_truenas_detection_prefers_local_execution(self) -> None:
        observed = []

        def mock_run(cmd, **kwargs):
            observed.append(cmd)
            return SimpleNamespace(returncode=0, stdout="TrueNAS-26.0.0-BETA.2")

        with patch.object(module.subprocess, "run", side_effect=mock_run):
            self.assertEqual(module.execution_target(), "truenas_local")
        self.assertEqual(observed, [["midclt", "call", "system.version"]])

    def test_non_truenas_uses_existing_ssh_alias(self) -> None:
        for result in (
            SimpleNamespace(returncode=1, stdout=""),
            SimpleNamespace(returncode=0, stdout="other-system"),
        ):
            with self.subTest(result=result), patch.object(
                module.subprocess, "run", return_value=result
            ):
                self.assertEqual(module.execution_target(), "workstation_ssh")

    def test_local_uses_existing_sudo_without_ssh_or_secret_output(self) -> None:
        commands = []

        def mock_run(cmd, **kwargs):
            commands.append(cmd)
            return SimpleNamespace(
                returncode=0,
                stdout="canonical_secret_file=available\nsecret_syntax=valid\n",
                stderr="sensitive-stderr-must-not-print",
            )

        with patch.object(module.subprocess, "run", side_effect=mock_run):
            mode, code, result = module.check("syntax", "truenas", "truenas_local")
        self.assertEqual((mode, code), ("syntax", 0))
        self.assertIn("syntax_status=complete", result)
        self.assertNotIn("sensitive-stderr", result)
        self.assertEqual(commands[0][:4], ["sudo", "-n", "python3", "-c"])
        self.assertEqual(commands[0][-1], "syntax")
        self.assertNotIn("ssh", commands[0])

    def test_remote_still_uses_verified_ssh_without_model_requests(self) -> None:
        commands = []

        def mock_run(cmd, **kwargs):
            commands.append(cmd)
            return SimpleNamespace(
                returncode=1, stdout="", stderr="sensitive-error"
            )

        with patch.object(module.subprocess, "run", side_effect=mock_run):
            mode, code, result = module.check("database", "truenas", "workstation_ssh")
        self.assertEqual((mode, code), ("database", 2))
        self.assertIn("database_status=unverified", result)
        self.assertNotIn("sensitive-error", result)
        command = commands[0]
        self.assertEqual(command[0], "ssh")
        self.assertIn("BatchMode=yes", command)
        self.assertIn("StrictHostKeyChecking=yes", command)
        self.assertNotIn("/v1/chat/completions", " ".join(command))

    def test_main_local_probe_never_invokes_ssh(self) -> None:
        with patch.object(module, "execution_target", return_value="truenas_local"), \
             patch.object(module, "check", side_effect=lambda m, h, t: (
                 m, 0, m + "_status=complete"
             )) as check, \
             patch.object(module.sys, "argv", ["script"]), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = module.main()
        self.assertEqual(code, 0)
        self.assertEqual(check.call_count, 3)
        self.assertIn("execution_target=truenas_local", output.getvalue())
        self.assertIn("database_status=complete", output.getvalue())


if __name__ == "__main__":
    unittest.main()
