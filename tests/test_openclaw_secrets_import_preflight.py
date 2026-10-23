"""Offline contracts for secret import preflight; no real credential material."""
import importlib.util
import io
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
import tempfile
from contextlib import redirect_stdout
import os
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/preflight-openclaw-secrets-import.py"
spec = importlib.util.spec_from_file_location("secret_import", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SecretImportPreflightTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.staging = Path(self.tmp.name) / "openclaw-import"
        self.staging.mkdir(mode=0o700)
        self.file = self.staging / "selected.env"
        self.file.write_text("DEMO_API_KEY=FAKE_NOT_A_REAL_CREDENTIAL\n")
        self.file.chmod(0o600)

    def test_private_staged_file_passes(self):
        self.assertEqual(module.preflight_file(self.file, self.staging), "private")

    def test_rejects_permissions_symlinks_and_other_locations(self):
        self.file.chmod(0o640)
        self.assertEqual(module.preflight_file(self.file, self.staging), "unsafe_file")
        self.file.chmod(0o600)
        alias = self.staging / "alias.env"
        alias.symlink_to(self.file)
        self.assertEqual(module.preflight_file(alias, self.staging), "unsafe_file")
        self.staging.chmod(0o755)
        self.assertEqual(module.preflight_file(self.file, self.staging), "unsafe_staging_directory")
        self.staging.chmod(0o700)
        self.assertEqual(module.preflight_file(self.file, Path(self.tmp.name)), "outside_private_staging")

    def test_rejects_empty_hardlinked_and_oversized_files(self):
        self.file.write_bytes(b"")
        self.assertEqual(module.preflight_file(self.file, self.staging), "unsafe_file")
        self.file.write_bytes(b"K=VALUE")
        alias = self.staging / "hardlink.env"
        os.link(self.file, alias)
        self.assertEqual(module.preflight_file(self.file, self.staging), "unsafe_file")
        alias.unlink()
        self.file.write_bytes(b"A" * (module.MAX_IMPORT_BYTES + 1))
        self.assertEqual(module.preflight_file(self.file, self.staging), "unsafe_file")

    def test_native_dryrun_never_writes_or_exposes_stdout(self):
        p = CompletedProcess([], 0, stdout=b"DO_NOT_PRINT_ME", stderr=b"SECRET")
        with patch.object(module.subprocess, "run", return_value=p) as run:
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(module.preflight_import(self.file), "native_accepted")
                self.assertEqual(output.getvalue(), "")
        command = run.call_args.args[0]
        self.assertEqual(command[-1], "--dry-run")
        self.assertEqual(command[:4], ["openclaw", "secrets", "store", "import"])
        self.assertIn("--kind", command)
        self.assertIn("secret", command)
        self.assertNotIn("DO_NOT_PRINT_ME", str(command))
        self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_native_failure_and_timeout_are_sanitized(self):
        with patch.object(module.subprocess, "run",
                          return_value=CompletedProcess([], 2, stdout=b"TOKEN")):
            self.assertEqual(module.preflight_import(self.file), "native_rejected")
        with patch.object(module.subprocess, "run", side_effect=TimeoutExpired("secret", 5)):
            self.assertEqual(module.preflight_import(self.file), "native_timeout")

    def test_main_never_invokes_cli_on_unsafe_file(self):
        self.file.chmod(0o644)
        with patch("sys.argv", ["preflight", "--file", str(self.file)]):
            with patch.object(Path, "home", return_value=Path(self.tmp.name)):
                with patch.object(module, "preflight_import") as action:
                    with redirect_stdout(io.StringIO()) as out:
                        self.assertEqual(module.main(), 2)
        action.assert_not_called()
        self.assertIn("secret_import_changed=false", out.getvalue())


if __name__ == "__main__":
    unittest.main()
