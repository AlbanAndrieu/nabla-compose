"""Hermetic workstation metadata diagnostics: never open any secret file."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/inspect-yubikey-workstation-readonly.py"
spec = importlib.util.spec_from_file_location("nabla_yubikey_workstation", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class WorkstationReadOnlyContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.uid = os.getuid()

    def test_absent_paths_do_not_pretend_configuration(self):
        with patch.object(mod.shutil, "which", return_value=None):
            report = mod.snapshot(self.home, self.uid)
        self.assertEqual(report["status"], "NO-GO")
        self.assertTrue(all(x == "MISSING" for x in report["tools"].values()))
        self.assertTrue(all(x == "NOT_FOUND" for x in report["paths"].values()))
        self.assertFalse(report["postgres_restore_verified"])
        self.assertFalse(report["hardware_mutation_authorized"])

    def test_installed_tool_is_not_proof_of_usage(self):
        with patch.object(mod.shutil, "which", return_value="/usr/bin/mock"):
            report = mod.snapshot(self.home, self.uid)
        self.assertEqual(report["tools"]["age-plugin-yubikey"], "INSTALLED_UNVERIFIED")
        self.assertFalse(report["age_decrypt_verified"])

    def test_sops_identity_is_metadata_only(self):
        path = self.home / ".config/sops/age/keys.txt"
        path.parent.mkdir(parents=True)
        path.write_text("SECRET-NOT-TO-BE-READ")
        path.chmod(0o600)
        self.assertEqual(mod.metadata(path, "identity", self.uid), "PRESENT_PRIVATE_METADATA_ONLY")
        path.chmod(0o644)
        self.assertEqual(mod.metadata(path, "identity", self.uid), "UNEXPECTED_METADATA")

    def test_symlink_is_refused(self):
        key = self.home / "keys.txt"
        key.write_text("fake")
        link = self.home / "other.age"
        link.symlink_to(key)
        self.assertEqual(mod.metadata(link, "identity", self.uid), "SYMLINK_REFUSED")

    def test_socket_is_only_presence_proof(self):
        path = self.home / "agent.sock"
        with socket.socket(socket.AF_UNIX) as sock:
            sock.bind(str(path))
            self.assertEqual(mod.metadata(path, "socket", self.uid), "PRESENT_UNVERIFIED")

    def test_public_handle_does_not_prove_ssh_login(self):
        path = self.home / "id_ed25519_sk.pub"
        path.write_text("public fixture")
        self.assertEqual(mod.metadata(path, "public", self.uid), "PRESENT_UNVERIFIED")

    def test_malformed_cli_does_not_scan(self):
        with patch.object(mod.sys, "argv", ["script", "--scan-secrets"]), \
             patch.object(mod, "snapshot") as read:
            self.assertEqual(mod.main(), 2)
        read.assert_not_called()

    def test_missing_home_fails_closed(self):
        with patch.object(mod.sys, "argv", ["script"]), \
             patch.dict(os.environ, {"HOME": "/unlikely_missing_nabla_yubikey_fixture_path"}), \
             patch("builtins.print") as output:
            self.assertEqual(mod.main(), 3)
        self.assertIn("HOME_UNAVAILABLE", output.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
