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
        inputs = iter([sensitive_a, sensitive_b])
        with patch.object(module, "read_escrow_state",
                          return_value="TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED") as target:
            self.assertEqual(module.inspect(tty=True,
                reader=lambda _prompt: next(inputs)),
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
            with self.subTest(exc=exc), \
                 patch.object(module, "discover_pair",
                              return_value=("DISCOVERY_NO_MATCHING_PAIR", None)), \
                 patch.object(module.getpass, "getpass", side_effect=exc):
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


    def test_known_backup_roots_include_workstation_and_mounted_copy(self):
        home = Path("/home/example")
        found = module.candidate_directories(home)
        self.assertEqual(found[0], home / ".local/share/nabla/age-backups")
        self.assertEqual(found[1], Path("/media/backup/lab/secret"))

    def test_discovery_matches_unique_basename_without_opening_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            a, b = base / "age-backups", base / "backup"
            a.mkdir(); b.mkdir()
            (a / "escrow-2026.age").write_bytes(b"ciphertext 1")
            (b / "escrow-2026.age").write_bytes(b"ciphertext 2")
            (a / "unrelated.age").write_bytes(b"different")
            with patch.object(module, "candidate_directories", return_value=(a,b)), \
                 patch.object(module, "read_escrow_state",
                    return_value="TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED") as meta:
                state,pair = module.discover_pair(base)
            self.assertEqual(state, "TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED")
            self.assertEqual(pair, (a / "escrow-2026.age", b / "escrow-2026.age"))
            meta.assert_called_once_with(*pair)

    def test_discovery_does_not_follow_symlinked_backup_directory(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            a = base / "good"; a.mkdir()
            shortcut = base / "link"
            shortcut.symlink_to(a, target_is_directory=True)
            with patch.object(module,"candidate_directories",return_value=(shortcut,a)), \
                 patch.object(module,"read_escrow_state") as meta:
                state,pair = module.discover_pair(base)
            self.assertEqual(state, "DISCOVERY_DIRECTORY_UNTRUSTED")
            self.assertIsNone(pair); meta.assert_not_called()

    def test_discovery_fails_closed_on_ambiguous_or_missing_pairs(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            a,b=Path(root)/"a",Path(root)/"b"
            a.mkdir(); b.mkdir()
            with patch.object(module,"candidate_directories",return_value=(a,b)):
                self.assertEqual(module.discover_pair(Path(root))[0],"DISCOVERY_NO_MATCHING_PAIR")
                for name in ("one.age","two.age"):
                    (a/name).write_bytes(b"one")
                    (b/name).write_bytes(b"two")
                self.assertEqual(module.discover_pair(Path(root))[0],"DISCOVERY_MULTIPLE_MATCHING_PAIRS")

    def test_discovery_ignores_symlinked_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            a,b=Path(root)/"a",Path(root)/"b"
            a.mkdir(); b.mkdir()
            (a/"matching.age").write_bytes(b"abc")
            (b/"matching.age").symlink_to(a/"matching.age")
            with patch.object(module,"candidate_directories",return_value=(a,b)):
                self.assertEqual(module.discover_pair(Path(root))[0], "DISCOVERY_NO_MATCHING_PAIR")

    def test_discovery_refuses_oversized_directories(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            a,b=Path(root)/"a",Path(root)/"b"
            a.mkdir(); b.mkdir()
            for i in range(module.DISCOVERY_LIMIT + 1):
                (a / f"file-{i}").touch()
            with patch.object(module,"candidate_directories",return_value=(a,b)):
                self.assertEqual(module.discover_pair(Path(root))[0],
                                 "DISCOVERY_TOO_MANY_ENTRIES")

    def test_inspect_can_accept_auto_discovered_pair_without_showing_paths(self):
        a = Path("/private/age-backups/escrow.age")
        b = Path("/media/backup/lab/secret/escrow.age")
        with patch.object(module,"discover_pair",
                return_value=("TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED",(a,b))), \
             patch.object(module, "read_escrow_state",
                return_value="TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED") as meta, \
             patch.object(module.getpass,"getpass") as manual:
            state = module.inspect(tty=True,confirmer=lambda prompt: "o")
        self.assertEqual(state,"TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED")
        meta.assert_called_once_with(a,b)
        manual.assert_not_called()

    def test_inspect_rejection_falls_back_to_manual_masked_input(self):
        a,b="/private/a.age","/private/b.age"
        prompts=iter([a,b])
        with patch.object(module,"discover_pair",
                return_value=("TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED",
                              (Path(a),Path(b)))), \
             patch.object(module.getpass,"getpass",
                side_effect=lambda prompt: next(prompts)), \
             patch.object(module,"read_escrow_state",
                return_value="SAME_FILESYSTEM") as meta:
            result=module.inspect(tty=True,confirmer=lambda prompt:"n")
        self.assertEqual(result,"SAME_FILESYSTEM")
        meta.assert_called_once_with(Path(a),Path(b))

    def test_discover_cli_redacts_paths_and_never_claims_restore(self):
        with patch.object(module,"discover_pair",
                return_value=("TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED",
                    (Path("/private/a.age"),Path("/secret/b.age")))), \
             redirect_stdout(io.StringIO()) as out:
            self.assertEqual(module.main(["--discover"]),0)
        record=json.loads(out.getvalue())
        self.assertNotIn("/private/",out.getvalue())
        self.assertNotIn("/secret/",out.getvalue())
        self.assertFalse(record["files_opened"])
        self.assertFalse(record["restoration_verified"])
        self.assertFalse(record["independent_media_verified"])



if __name__ == "__main__":
    unittest.main()
