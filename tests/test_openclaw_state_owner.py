"""Security contracts for read-only OpenClaw SQLite holder attribution."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/diagnose-openclaw-state-owner.py"
spec = importlib.util.spec_from_file_location("openclaw_state_owner", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class OwnerEvidenceContracts(unittest.TestCase):
    def test_parses_last_contention_and_not_unrelated_pid(self):
        lines = [
            "not an error pid 1111",
            "GatewayStateOwnerContentionError: state database is busy",
            "holder 3713 at home, last renewed 104622s ago",
            "Some other process 9999",
            "GatewayStateOwnerContentionError: state database is busy",
            "holder 4242 at home, last renewed 3s ago",
        ]
        self.assertEqual(mod.holder_from_lines(lines), 4242)
        self.assertIsNone(mod.holder_from_lines(["no holder 3713"]),
                          )
        self.assertIsNone(mod.holder_from_lines([
            "GatewayStateOwnerContentionError", "token sk-PRIVATE"]))

    def test_decisions_never_equate_historical_log_with_live_owner(self):
        rows = (
            ((3713, "exited", set()), "historical_holder_no_current_opener"),
            ((3713, "other_process", set()), "logged_pid_alive_without_sqlite_opener"),
            ((3713, "gateway_process", {3713}), "logged_holder_still_has_state_file_open"),
            ((3713, "gateway_process", {3817}), "different_sqlite_opener_observed"),
            ((3713, "gateway_process", None), "current_owner_unverified"),
            ((None, "not_found", set()), "logged_holder_unknown"),
        )
        for input_, expected in rows:
            with self.subTest(expected=expected):
                self.assertEqual(mod.decide(*input_), expected)

    def test_no_raw_log_or_command_args_are_reported(self):
        fake_source = SimpleNamespace(file_log_sample=lambda: (
            ["token sk-PRIVATE", "GatewayStateOwnerContentionError: state database is busy",
             "holder 3713 at /home/PRIVATE"], "private_file_tail"))
        with patch.object(mod, "previous_diagnostics", return_value=fake_source), \
             patch.object(mod, "safe_sqlite_files", return_value=[Path("/tmp/db")]), \
             patch.object(mod, "safe_native_lock_files", return_value=[]), \
             patch.object(mod, "opener_pids", return_value={3713}), \
             patch.object(mod, "process_category", return_value="gateway_process"), \
             patch.object(mod, "service_state", return_value="failed"), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(), 0)
        text = output.getvalue()
        self.assertIn("state_owner_diagnosis=logged_holder_still_has_state_file_open", text)
        self.assertIn("logged_holder_process=gateway_process", text)
        for secret in ("PRIVATE", "sk-", "/home", "3713"):
            self.assertNotIn(secret, text)

    def test_older_contention_no_longer_has_owner(self):
        fake_source = SimpleNamespace(file_log_sample=lambda: (
            ["GatewayStateOwnerContentionError", "holder 3713"], "private_file_tail"))
        with patch.object(mod, "previous_diagnostics", return_value=fake_source), \
             patch.object(mod, "safe_sqlite_files", return_value=[Path("/tmp/db")]), \
             patch.object(mod, "safe_native_lock_files", return_value=[]), \
             patch.object(mod, "opener_pids", return_value=set()), \
             patch.object(mod, "process_category", return_value="exited"), \
             patch.object(mod, "service_state", return_value="failed"), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(), 0)
        self.assertIn("historical_holder_no_current_opener", output.getvalue())
        self.assertIn("historical_pid_reuse_ruled_out=false", output.getvalue())

    def test_fuser_output_is_parsed_without_printing_pid(self):
        files = [Path("/tmp/example-oc.sqlite")]
        with patch.object(mod.subprocess, "run",
                          return_value=SimpleNamespace(returncode=0, stdout=b"3713 4242\n",
                                                       stderr=b"private location")):
            self.assertEqual(mod.opener_pids(files), {3713, 4242})
        with patch.object(mod.subprocess, "run",
                          return_value=SimpleNamespace(returncode=1, stdout=b"",
                                                       stderr=b"")):
            self.assertEqual(mod.opener_pids(files), set())
        with patch.object(mod.subprocess, "run",
                          return_value=SimpleNamespace(returncode=127, stdout=b"",
                                                       stderr=b"")):
            self.assertIsNone(mod.opener_pids(files))

    def test_database_symlink_refused_without_accessing_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = root / "state"
            state.mkdir()
            target = root / "other"
            target.write_text("PRIVATE data")
            (state / "openclaw.sqlite").symlink_to(target)
            with patch.dict(os.environ, {"OPENCLAW_STATE_DIR": str(root)}):
                self.assertIsNone(mod.safe_sqlite_files())

    def test_native_state_lock_is_discovered_but_never_read(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            locks = root / "state/locks/openclaw-state-owners"
            locks.mkdir(parents=True)
            for directory in (root / "state/locks", locks):
                directory.chmod(0o700)
            lock = locks / "state.abc123456.lock"
            lock.write_bytes(b"PRIVATE lease data")
            lock.chmod(0o600)
            with patch.dict(os.environ, {"OPENCLAW_STATE_DIR": str(root)}):
                self.assertEqual(mod.safe_native_lock_files(), [lock])

    def test_symlink_native_lock_path_is_not_followed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            locks = root / "state/locks/openclaw-state-owners"
            locks.mkdir(parents=True)
            for directory in (root / "state/locks", locks):
                directory.chmod(0o700)
            target = root / "secret"
            target.write_text("PRIVATE")
            (locks / "state.abc123456.lock").symlink_to(target)
            with patch.dict(os.environ, {"OPENCLAW_STATE_DIR": str(root)}):
                self.assertIsNone(mod.safe_native_lock_files())

    def test_native_owner_counts_even_with_no_open_sqlite_file(self):
        fake_source = SimpleNamespace(file_log_sample=lambda: (
            ["GatewayStateOwnerContentionError", "holder 3713"],
            "private_file_tail"))
        native = Path("/tmp/opaque-owner-lock")
        def mock_fuser(files):
            self.assertEqual(files, [native])
            return {3713}
        with patch.object(mod, "previous_diagnostics", return_value=fake_source), \
             patch.object(mod, "safe_sqlite_files", return_value=[]), \
             patch.object(mod, "safe_native_lock_files", return_value=[native]), \
             patch.object(mod, "opener_pids", side_effect=mock_fuser), \
             patch.object(mod, "process_category", return_value="gateway_process"), \
             patch.object(mod, "service_state", return_value="failed"), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(), 0)
        self.assertIn("native_lock_inventory=present", output.getvalue())
        self.assertIn("logged_holder_in_state_openers=yes", output.getvalue())
        self.assertIn("logged_holder_still_has_state_file_open", output.getvalue())

    def test_current_process_is_classified_without_disclosing_arguments(self):
        kind = mod.process_category(os.getpid())
        self.assertIn(kind, ("other_process", "unverified"))
        self.assertEqual(mod.process_category(None), "unverified")


if __name__ == "__main__":
    unittest.main()
