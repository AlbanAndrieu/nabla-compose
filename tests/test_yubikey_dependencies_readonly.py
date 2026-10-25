"""Hermetic contracts: metadata-only GPG/PCSC/SSH/recovery dependencies."""
from __future__ import annotations

import importlib.util
import io
import json
import stat
import subprocess
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts/workstation/inspect-yubikey-dependencies-readonly.py"
spec = importlib.util.spec_from_file_location("yubi_dependencies_readonly", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DependencyContracts(unittest.TestCase):
    def test_process_presence_is_not_card_proof(self):
        with patch.object(module.shutil, "which", return_value="/usr/bin/pgrep"), \
             patch.object(module.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
            self.assertEqual(module.process_state("scdaemon", uid=1000), "PROCESS_PRESENT_UNVERIFIED")
        self.assertEqual(run.call_args.args[0], ["pgrep", "-x", "-u", "1000", "scdaemon"])
        for name in ("stdin", "stdout", "stderr"):
            self.assertEqual(run.call_args.kwargs[name], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["timeout"], 4)
        self.assertFalse(run.call_args.kwargs["check"])

    def test_process_not_observed_and_unrecognized_error(self):
        with patch.object(module.shutil, "which", return_value="/usr/bin/pgrep"):
            for rc, expected in [(1, "PROCESS_NOT_OBSERVED"), (2, "UNKNOWN")]:
                with patch.object(module.subprocess, "run", return_value=SimpleNamespace(returncode=rc)):
                    self.assertEqual(module.process_state("pcscd"), expected)

    def test_process_timeout_and_absent_tool_fail_closed(self):
        with patch.object(module.shutil, "which", return_value=None), \
             patch.object(module.subprocess, "run") as run:
            self.assertEqual(module.process_state("scdaemon"), "TOOL_MISSING")
            run.assert_not_called()
        with patch.object(module.shutil, "which", return_value="pgrep"), \
             patch.object(module.subprocess, "run", side_effect=subprocess.TimeoutExpired(["pgrep"], 4)):
            self.assertEqual(module.process_state("pcscd"), "UNKNOWN")

    def test_process_unknown_name_is_never_queried(self):
        with patch.object(module.subprocess, "run") as run:
            self.assertEqual(module.process_state("gpg-agent --kill"), "UNKNOWN")
            run.assert_not_called()

    def test_absent_ssh_socket_never_contacts_agent(self):
        with patch.dict(module.os.environ, {}, clear=True), patch.object(module.subprocess, "run") as run:
            self.assertEqual(module.ssh_agent_state(), "SOCKET_NOT_CONFIGURED")
            run.assert_not_called()

    def test_ssh_socket_invalid_path_and_symlink_block(self):
        with patch.dict(module.os.environ, {"SSH_AUTH_SOCK": "relative"}), \
             patch.object(module.subprocess, "run") as run:
            self.assertEqual(module.ssh_agent_state(), "UNKNOWN")
            run.assert_not_called()
        with patch.dict(module.os.environ, {"SSH_AUTH_SOCK": "/tmp/agent"}), \
             patch.object(module.Path, "lstat", return_value=SimpleNamespace(
                 st_mode=stat.S_IFLNK | 0o777, st_uid=module.os.getuid())), \
             patch.object(module.subprocess, "run") as run:
            self.assertEqual(module.ssh_agent_state(), "SOCKET_UNTRUSTED")
            run.assert_not_called()

    def test_ssh_agent_public_only_and_masked(self):
        with patch.dict(module.os.environ, {"SSH_AUTH_SOCK": "/tmp/agent"}), \
             patch.object(module.Path, "lstat", return_value=SimpleNamespace(
                 st_mode=stat.S_IFSOCK | 0o600, st_uid=module.os.getuid())), \
             patch.object(module.shutil, "which", return_value="/usr/bin/ssh-add"), \
             patch.object(module.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
            self.assertEqual(module.ssh_agent_state(), "PUBLIC_IDENTITIES_PRESENT_UNVERIFIED")
        self.assertEqual(run.call_args.args[0], ["ssh-add", "-l"])
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["timeout"], 5)

    def test_ssh_none_or_failure_is_not_success(self):
        with patch.dict(module.os.environ, {"SSH_AUTH_SOCK": "/tmp/agent"}), \
             patch.object(module.Path, "lstat", return_value=SimpleNamespace(
                 st_mode=stat.S_IFSOCK | 0o600, st_uid=module.os.getuid())), \
             patch.object(module.shutil, "which", return_value="ssh-add"):
            for rc, expected in [(1, "NO_IDENTITIES_OR_AGENT"), (2, "UNKNOWN"), (255, "UNKNOWN")]:
                with patch.object(module.subprocess, "run", return_value=SimpleNamespace(returncode=rc)):
                    self.assertEqual(module.ssh_agent_state(), expected)
            with patch.object(module.subprocess, "run", side_effect=OSError("secret")):
                self.assertEqual(module.ssh_agent_state(), "UNKNOWN")

    def test_recovery_tools_presence_only(self):
        with patch.object(module, "process_state", return_value="PROCESS_NOT_OBSERVED"), \
             patch.object(module, "ssh_agent_state", return_value="SOCKET_NOT_CONFIGURED"), \
             patch.object(module.shutil, "which", side_effect=lambda x: "/bin/fake" if x=="pg_restore" else None):
            report = module.snapshot()
        self.assertEqual(report["recovery_tools"]["pg_restore"], "INSTALLED_UNVERIFIED")
        self.assertEqual(report["recovery_tools"]["psql"], "MISSING")
        for key in ("openpgp_card_access_verified", "postgres_restore_verified",
                    "ssh_fido_login_verified", "escrow_restore_verified",
                    "hardware_mutation_authorized"):
            self.assertFalse(report[key])
        self.assertEqual(report["status"], "NO-GO")

    def test_arguments_rejected_before_snapshot(self):
        with patch.object(module, "snapshot") as snap, redirect_stderr(io.StringIO()):
            self.assertEqual(module.main(["--pin"]), 2)
            snap.assert_not_called()

    def test_json_report_has_no_identifiers_or_paths(self):
        with patch.object(module, "snapshot", return_value={"status": "NO-GO", "hardware_mutation_authorized": False}):
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(module.main([]), 0)
            self.assertEqual(json.loads(out.getvalue())["status"], "NO-GO")


if __name__ == "__main__":
    unittest.main()
