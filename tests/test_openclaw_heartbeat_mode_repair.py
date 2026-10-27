"""Offline, metadata-only permission repair contract for historic OpenClaw files."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/secure-openclaw-heartbeat-copies.py"
spec = importlib.util.spec_from_file_location("secure_heartbeat", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class PermissionRepairTests(unittest.TestCase):
    def fixtures(self, root: Path):
        files = [
            ("workspace_before_fix", root / "HEARTBEAT.md.before-fix",
             "HEARTBEAT.md.before-fix"),
            ("nabla_legacy_heartbeat", root / "HEARTBEAT.md", "HEARTBEAT.md"),
            ("openclaw_august_archive", root / "openclaw-2026-08-04_0220.tar.gz",
             "openclaw-2026-08-04_0220.tar.gz"),
        ]
        for _, path, _ in files:
            path.write_bytes(b"PRIVATE-SENTINEL-NOT-TO-PRINT")
            path.chmod(0o600)
        return files

    def test_check_succeeds_with_private_files_without_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            entries = self.fixtures(Path(td))
            report, code = mod.reconcile(entries, apply=False)
            self.assertEqual(code, 0)
            self.assertTrue(report["all_private"])
            self.assertFalse(report["content_read"])
            self.assertFalse(report["archive_extracted"])
            self.assertEqual(report["files_mode_updated"], 0)
            self.assertNotIn("PRIVATE-SENTINEL", json.dumps(report))

    def test_check_fails_and_explicit_apply_restricts_all_three(self):
        with tempfile.TemporaryDirectory() as td:
            entries = self.fixtures(Path(td))
            for (_, path, _), mode in zip(entries, (0o666, 0o644, 0o644)):
                path.chmod(mode)
            first, status = mod.reconcile(entries, apply=False)
            self.assertEqual(status, 2)
            self.assertFalse(first["all_private"])
            self.assertEqual(first["files_mode_updated"], 0)
            for _, path, _ in entries:
                self.assertNotEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            second, status = mod.reconcile(entries, apply=True)
            self.assertEqual(status, 0)
            self.assertEqual(second["files_mode_updated"], 3)
            for _, path, _ in entries:
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertEqual(path.read_bytes(), b"PRIVATE-SENTINEL-NOT-TO-PRINT")

    def test_missing_file_blocks_apply_before_any_chmod(self):
        with tempfile.TemporaryDirectory() as td:
            entries = self.fixtures(Path(td))
            entries[0][1].chmod(0o666)
            entries[-1][1].unlink()
            report, status = mod.reconcile(entries, apply=True)
            self.assertEqual(status, 2)
            self.assertFalse(report["all_private"])
            self.assertEqual(report["files_mode_updated"], 0)
            self.assertEqual(stat.S_IMODE(entries[0][1].stat().st_mode), 0o666)

    def test_symlink_or_hardlink_blocks_apply(self):
        with tempfile.TemporaryDirectory() as td:
            entries = self.fixtures(Path(td))
            entries[0][1].chmod(0o644)
            entries[1][1].unlink()
            entries[1][1].symlink_to(entries[0][1])
            _, status = mod.reconcile(entries, apply=True)
            self.assertEqual(status, 2)
            self.assertEqual(stat.S_IMODE(entries[0][1].stat().st_mode), 0o644)

    def test_wrong_filename_blocks_apply(self):
        with tempfile.TemporaryDirectory() as td:
            entries = self.fixtures(Path(td))
            entries[1] = (entries[1][0], entries[1][1], "WRONG.md")
            _, status = mod.reconcile(entries, apply=True)
            self.assertEqual(status, 2)

    def test_unexpected_owner_blocks_change(self):
        with tempfile.TemporaryDirectory() as td:
            entries = self.fixtures(Path(td))
            entries[0][1].chmod(0o644)
            with patch.object(mod.os, "geteuid", return_value=os.geteuid() + 111):
                report, status = mod.reconcile(entries, apply=True)
            self.assertEqual(status, 2)
            self.assertEqual(report["files_mode_updated"], 0)
            self.assertEqual(stat.S_IMODE(entries[0][1].stat().st_mode), 0o644)


if __name__ == "__main__":
    unittest.main()
