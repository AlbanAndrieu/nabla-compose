"""Offline guardrails for bulk runtime-secret mode repair."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/audit-runtime-secret-permissions.py"
spec = importlib.util.spec_from_file_location("permissions_scope", SCRIPT)
assert spec is not None and spec.loader is not None
MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MODULE)


class SecretModeAuditTest(unittest.TestCase):
    def test_secret_filenames_allowlisted(self):
        self.assertTrue(MODULE.is_secret_name(".env"))
        self.assertTrue(MODULE.is_secret_name(".env.secrets"))
        self.assertTrue(MODULE.is_secret_name(".env.compose"))
        self.assertTrue(MODULE.is_secret_name(".env.litellm.secrets"))
        for name in ("config.yaml", "keys.txt", "private.pem", ".bashrc"):
            self.assertFalse(MODULE.is_secret_name(name))

    def test_apply_blocked_outside_canonical_trueNAS_root(self):
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--apply", "--root", temp,
                 "--acknowledge", MODULE.ACK],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--apply requires canonical root", result.stderr)

    def test_apply_needs_exact_acknowledgement(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--apply", "--acknowledge", "YES"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2)

    def test_refuse_symlink_and_non_root_owner_without_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "sample.env").write_text("FAKE=offline\n")
            (path / ".env.secrets").write_text("FAKE=offline\n")
            (path / "outside").symlink_to("/tmp", target_is_directory=True)
            changes, issues = MODULE.plan(path)
            self.assertFalse(changes)
            self.assertTrue(any("SYMLINK" in issue for issue in issues))
            # The current user owns synthetic files, and the script must
            # refuse to chown them blindly.
            self.assertTrue(any("NON_ROOT_OWNER" in issue for issue in issues))

    def test_never_read_or_echo_secret_values(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn(".read_text(", source)
        self.assertNotIn(".read_bytes(", source)
        self.assertNotIn("os.chown(", source)
        self.assertNotIn("chmod -R", source)
        self.assertIn("os.O_NOFOLLOW", source)


if __name__ == "__main__":
    unittest.main()
