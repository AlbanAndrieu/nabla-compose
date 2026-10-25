"""Offline contracts for idempotent, fail-closed TrueNAS SSH tunnel setup."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
from subprocess import CompletedProcess
import unittest
from unittest.mock import mock_open, patch
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/ensure-openclaw-truenas-litellm-tunnel.py"
spec = importlib.util.spec_from_file_location("ssh_tunnel_check", SCRIPT)
tunnel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tunnel)


class SSHTunnelContracts(unittest.TestCase):
    def test_validates_ssh_forward_forms_and_expected_destination(self):
        self.assertTrue(tunnel.expected_forward(
            ["ssh", "-N", "-L", tunnel.FORWARD, "albandrieu@172.17.0.24"]))
        self.assertTrue(tunnel.expected_forward(
            ["ssh", "-fN", "-L" + tunnel.FORWARD, "truenas"]))
        self.assertFalse(tunnel.expected_forward(
            ["ssh", "-L", "0.0.0.0:14000:127.0.0.1:4000", "truenas"]))
        self.assertFalse(tunnel.expected_forward(
            ["ssh", "-L", tunnel.FORWARD, "untrusted-host.invalid"]))
        self.assertFalse(tunnel.expected_forward(["ssh", "-N", "truenas"]))

    def test_rejects_wrong_ssh_config_target_and_port(self):
        correct = b"hostname 172.17.0.24\nuser albandrieu\nport 9922\n"
        with patch.object(tunnel, "execute", return_value=CompletedProcess([], 0, correct, b"")):
            self.assertTrue(tunnel.ssh_alias_valid())
        # The user's ~/.ssh/config uses: Host 172.17.0.24 nabla freenas truenas
        # without a HostName directive. OpenSSH then returns "hostname truenas".
        multi_alias = b"hostname truenas\nuser albandrieu\nport 9922\n"
        with patch.object(tunnel, "execute", return_value=CompletedProcess([], 0, multi_alias, b"")):
            self.assertTrue(tunnel.ssh_alias_valid())
        for config in (b"hostname 172.17.0.57\nuser albandrieu\nport 9922",
                       b"hostname 172.17.0.24\nuser albandrieu\nport 22",
                       b"hostname 172.17.0.24\nuser root\nport 9922"):
            with patch.object(tunnel, "execute", return_value=CompletedProcess([], 0, config, b"")):
                self.assertFalse(tunnel.ssh_alias_valid())

    def test_ss_proves_existing_ssh_local_forward_without_printing_pid(self):
        line = b'LISTEN 0 128 127.0.0.1:14000 0.0.0.0:* users:(("ssh",pid=1167958,fd=4))\n'
        argv = b"ssh\x00-N\x00-L\x00" + tunnel.FORWARD.encode() + b"\x00albandrieu@172.17.0.24\x00"
        with patch.object(tunnel, "execute", return_value=CompletedProcess([], 0, line, b"")), \
             patch.object(tunnel.os, "stat", return_value=SimpleNamespace(st_uid=os.geteuid())), \
             patch("builtins.open", mock_open(read_data=argv)):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(tunnel.main(["--check"]), 0)
        self.assertIn("truenas_tunnel=verified_ssh", output.getvalue())
        self.assertNotIn("1167958", output.getvalue())
        self.assertNotIn("albandrieu", output.getvalue())

    def test_occupied_by_other_process_fails_closed_no_new_ssh(self):
        line = b'LISTEN 0 128 127.0.0.1:14000 0.0.0.0:* users:(("python3",pid=1234,fd=4))\n'
        with patch.object(tunnel, "execute", return_value=CompletedProcess([], 0, line, b"")) as execute:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(tunnel.main(["--ensure"]), 2)
        execute.assert_called_once()
        self.assertIn("truenas_tunnel=occupied_unverified", output.getvalue())
        self.assertIn("truenas_tunnel_action=blocked", output.getvalue())

    def test_no_listener_check_does_not_create_tunnel(self):
        with patch.object(tunnel, "execute", return_value=CompletedProcess([], 0, b"", b"")) as execute:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(tunnel.main(["--check"]), 2)
        execute.assert_called_once()
        self.assertIn("truenas_tunnel_action=not_started", output.getvalue())

    def test_create_only_after_approved_alias_and_verify_started_ssh(self):
        responses = [CompletedProcess([], 0, b"", b"")]
        with patch.object(tunnel, "listener_status", side_effect=["absent", "verified_ssh"]), \
             patch.object(tunnel, "ssh_alias_valid", return_value=True), \
             patch.object(tunnel, "execute", return_value=CompletedProcess([], 0, b"", b"")) as execute:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(tunnel.main(["--ensure"]), 0)
        cmd = execute.call_args.args[0]
        self.assertEqual(cmd[0], "ssh")
        self.assertIn("StrictHostKeyChecking=yes", cmd)
        self.assertIn("ForwardAgent=no", cmd)
        self.assertIn("ExitOnForwardFailure=yes", cmd)
        self.assertIn("none", cmd)
        self.assertIn(tunnel.FORWARD, cmd)
        self.assertIn("HostName=172.17.0.24", cmd)
        self.assertNotIn("LITELLM_MASTER_KEY", " ".join(cmd))
        self.assertIn("truenas_tunnel_after_start=verified_ssh", output.getvalue())

    def test_bad_alias_refuses_to_launch_ssh(self):
        with patch.object(tunnel, "listener_status", return_value="absent"), \
             patch.object(tunnel, "ssh_alias_valid", return_value=False), \
             patch.object(tunnel, "execute") as execute:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(tunnel.main(["--ensure"]), 2)
        execute.assert_not_called()
        self.assertIn("truenas_ssh_alias=unexpected_target_or_port", output.getvalue())

    def test_duplicate_ssh_listener_does_not_start_another(self):
        with patch.object(tunnel, "listener_status", return_value="verified_ssh"), \
             patch.object(tunnel, "execute") as execute:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(tunnel.main(["--ensure"]), 0)
        execute.assert_not_called()
        self.assertIn("truenas_tunnel_action=reuse", output.getvalue())


if __name__ == "__main__":
    unittest.main()
