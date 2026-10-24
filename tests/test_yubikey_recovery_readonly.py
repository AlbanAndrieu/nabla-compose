"""Hermetic public OTP2 and escrow-metadata contracts. Never accesses real secrets."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts/workstation/inspect-yubikey-recovery-readonly.py"
spec = importlib.util.spec_from_file_location("nabla_recovery_readonly", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RecoveryReadOnlyContracts(unittest.TestCase):
    replies = {
        ("list", "--serials"): (0, "22916048\n"),
        ("--device", "22916048", "info"): (0, "Firmware version: 5.4.3\n"),
        ("--device", "22916048", "otp", "info"): (
            0, "Slot 1: programmed\nSlot 2: programmed\n"
        ),
    }

    def otp(self, changes=None):
        mapping = dict(self.replies)
        mapping.update(changes or {})
        seen = []

        def run(*args):
            seen.append(args)
            return mapping[args]

        with patch.object(module, "public_command", side_effect=run):
            state = module.otp2_inventory()
        return state, seen

    def test_programmed_proves_only_slot_presence(self):
        state, seen = self.otp()
        self.assertEqual(state, "PROGRAMMED_TYPE_UNVERIFIED")
        self.assertEqual(len(seen), 3)

    def test_empty_slot_does_not_become_programmed(self):
        state, _ = self.otp({
            ("--device", "22916048", "otp", "info"): (0, "Slot 2: empty\n")
        })
        self.assertEqual(state, "EMPTY")

    def test_wrong_or_multiple_yubikeys_block_otp_reads(self):
        for detected in ("23501671\n", "22916048\n23501671\n"):
            with self.subTest(detected=detected):
                state, seen = self.otp({("list", "--serials"): (0, detected)})
                self.assertEqual(state, "UNKNOWN")
                self.assertEqual(len(seen), 1)

    def test_reader_failure_and_changed_firmware_fail_closed(self):
        for change in (
            {("list", "--serials"): (1, "")},
            {("--device", "22916048", "info"): (0, "Firmware version: 5.7.4\n")},
            {("--device", "22916048", "otp", "info"): (2, "Slot 2: programmed\n")},
        ):
            self.assertEqual(self.otp(change)[0], "UNKNOWN")

    def test_conflicting_status_is_unknown(self):
        state, _ = self.otp({
            ("--device", "22916048", "otp", "info"):
                (0, "Slot 2: programmed\nSlot 2: empty\n")
        })
        self.assertEqual(state, "UNKNOWN")

    def test_only_approved_public_commands_no_stdin(self):
        with patch.object(module.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, "22916048\n", "")) as run:
            module.public_command("list", "--serials")
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertTrue(run.call_args.kwargs["capture_output"])
        with self.assertRaises(ValueError):
            module.public_command("--device", "22916048", "otp", "calculate", "2")

    def test_escrow_same_file_and_filesystem_are_not_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / "first.age"
            second = Path(folder) / "second.age"
            first.write_bytes(b"ciphertext fixture")
            second.write_bytes(b"another ciphertext fixture")
            self.assertEqual(module.escrow_inventory(first, first), "SAME_FILE")
            self.assertEqual(module.escrow_inventory(first, second), "SAME_FILESYSTEM")
            second.unlink()
            os.link(first, second)
            self.assertEqual(module.escrow_inventory(first, second), "SAME_FILE")

    def test_invalid_file_and_symlink_are_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / "first.age"
            second = Path(folder) / "second.age"
            first.write_bytes(b"ciphertext fixture")
            second.symlink_to(first)
            self.assertEqual(module.escrow_inventory(first, second), "UNKNOWN")
            self.assertEqual(module.escrow_inventory(first, Path(folder) / "missing.age"), "UNKNOWN")

    def test_distinct_filesystems_are_not_automatic_recovery(self):
        with patch.object(module, "file_metadata",
                          side_effect=[(True, 10, 1), (True, 20, 2)]):
            state = module.escrow_inventory(Path("/tmp/a.age"), Path("/tmp/b.age"))
        self.assertEqual(state, "TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED")

    def test_json_report_never_proves_secrets_or_authorizes_mutation(self):
        with patch.object(sys, "argv", ["read-only", "--otp2-secondary"]), \
             patch.object(module, "otp2_inventory", return_value="PROGRAMMED_TYPE_UNVERIFIED"), \
             patch("builtins.print") as output:
            self.assertEqual(module.main(), 0)
        report = json.loads(output.call_args.args[0])
        self.assertEqual(report["status"], "NO-GO")
        self.assertFalse(report["otp2_hmac_sha1_verified"])
        self.assertFalse(report["keepassxc_verified"])
        self.assertFalse(report["hardware_mutation_authorized"])

    def test_cli_requires_explicit_scope_without_touching_hardware(self):
        with patch.object(sys, "argv", ["read-only"]), \
             patch.object(module, "otp2_inventory") as otp:
            with self.assertRaises(SystemExit) as caught:
                module.main()
        self.assertEqual(caught.exception.code, 2)
        otp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
