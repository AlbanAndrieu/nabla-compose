"""Hermetic tests: escrow path input is private and never decrypts."""
from __future__ import annotations
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts/workstation/inspect-yubikey-escrow-pair-interactive.py"
spec = importlib.util.spec_from_file_location("nabla_escrow_private_input", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Contracts(unittest.TestCase):
    def test_check_never_prompts_or_reads_backup(self):
        with patch.object(module, "inspect") as inspect, redirect_stdout(io.StringIO()) as out:
            self.assertEqual(module.main(["--check"]), 0)
            inspect.assert_not_called()
        result = json.loads(out.getvalue())
        self.assertEqual(result["state"], "PATHS_NOT_COLLECTED")
        self.assertFalse(result["restoration_verified"])

    def test_unknown_arguments_block_before_prompt(self):
        with patch.object(module, "inspect") as inspect, redirect_stderr(io.StringIO()):
            for argv in (["--inspect"], ["--inspect", "--acknowledge", "other"],
                         ["--check", "--acknowledge", module.ACK], ["--decrypt"], []):
                with self.subTest(argv=argv), self.assertRaises(SystemExit) as err:
                    module.main(argv)
                self.assertEqual(err.exception.code, 2)
            inspect.assert_not_called()

    def test_no_tty_prevents_input(self):
        with patch.object(module.getpass, "getpass") as reader:
            self.assertEqual(module.inspect(tty=False), "INTERACTIVE_TERMINAL_REQUIRED")
            reader.assert_not_called()

    def test_successful_inspection_returns_only_classification(self):
        sensitive_a = "/mnt/private-disk/a/backup.age"
        sensitive_b = "/mnt/offsite/b/backup.age"
        with patch.object(module, "read_escrow_state",
                          return_value="TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED") as target:
            self.assertEqual(module.inspect(tty=True,
                reader=iter([sensitive_a, sensitive_b]).__next__),
                "TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED")
        args = target.call_args.args
        self.assertEqual(args, (Path(sensitive_a), Path(sensitive_b)))
        self.assertIsInstance(args[0], Path)

    def test_reject_relative_invalid_and_duplicate_paths_before_stat(self):
        with patch.object(module, "read_escrow_state") as read:
            for a, b, expected in (
                ("relative/a.age", "/abs/b.age", "INVALID_INPUT"),
                ("/a/a.txt", "/b/b.age", "INVALID_INPUT"),
                ("/a/backup.age", "/a/backup.age", "SAME_FILE"),
                ("/a/a.age\n", "/b/b.age", "INVALID_INPUT"),
                ("/a/a.age\x00", "/b/b.age", "INVALID_INPUT"),
                ("", "/b/b.age", "INVALID_INPUT"),
            ):
                with self.subTest(a=a[:5]):
                    self.assertEqual(module.classify_inputs(a, b), expected)
            read.assert_not_called()

    def test_input_interrupt_never_raises(self):
        for exc in (EOFError, KeyboardInterrupt, OSError):
            with self.subTest(exc=exc), patch.object(module.getpass, "getpass", side_effect=exc):
                self.assertEqual(module.inspect(tty=True), "INPUT_UNAVAILABLE")

    def test_main_redacts_paths_and_never_claims_independent_media(self):
        with patch.object(module, "inspect",
                          return_value="TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED"), \
             patch.object(module.os, "isatty", return_value=True), \
             redirect_stdout(io.StringIO()) as out:
            self.assertEqual(module.main(["--inspect", "--acknowledge", module.ACK]), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["status"], "NO-GO")
        self.assertFalse(result["paths_disclosed"])
        self.assertFalse(result["files_opened"])
        self.assertFalse(result["independent_media_verified"])
        self.assertFalse(result["decryption_attempted"])
        self.assertFalse(result["restoration_verified"])

    def test_unavailable_inspector_fails_closed(self):
        with patch.object(module.importlib.util, "spec_from_file_location", return_value=None):
            self.assertEqual(module.read_escrow_state(Path("/a.age"), Path("/b.age")),
                             "METADATA_INSPECTOR_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
