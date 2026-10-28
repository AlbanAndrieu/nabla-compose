"""Hermetic inventory of legacy encrypted OpenClaw configuration, no secret reads."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / "scripts/workstation/audit-openclaw-nabla-migration.py"
SPEC = importlib.util.spec_from_file_location("nabla_migration", SRC)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class MigrationAuditTests(unittest.TestCase):
    def test_locked_heartbeat_is_not_copied(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            dest = root / "workspace"
            dest.mkdir(mode=0o700)
            (dest / "HEARTBEAT.md").write_bytes(mod.GITCRYPT_MAGIC + b"encrypted fake")
            (dest / "HEARTBEAT.md").chmod(0o600)  # independent of caller umask
            result = mod.inventory(root)
            heartbeat = next(x for x in result["known_files"] if x["role"] == "workspace/HEARTBEAT.md")
            self.assertEqual(heartbeat["source_status"], "gitcrypt_locked")
            self.assertFalse(heartbeat["auto_publish"])
            self.assertFalse(result["heartbeat_reactivated"])
            self.assertFalse(result["secrets_copied"])
            self.assertFalse(result["runtime_changed"])

    def test_public_migration_excludes_secret_state(self):
        self.assertFalse(any("auth-profiles" in name or ".env" in name
                             or "sqlite" in name or "openclaw.json" in name
                             for name in mod.REVIEW))

    def test_restricted_personal_files_are_never_read(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            parent = root / "workspace"
            parent.mkdir()
            (parent / "USER.md").write_text("PRIVATE-CANARY")
            (parent / "USER.md").chmod(0o600)  # independent of caller umask
            result = mod.inventory(root)
            record = next(x for x in result["known_files"] if x["role"] == "workspace/USER.md")
            self.assertEqual(record["source_status"], "present_not_inspected")
            self.assertNotIn("PRIVATE-CANARY", json.dumps(result))

    def test_symlink_root_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            actual = root / "real"
            actual.mkdir()
            alias = root / "link"
            alias.symlink_to(actual, target_is_directory=True)
            self.assertEqual(mod.inventory(alias)["migration_status"], "legacy_root_unavailable")

    def test_file_symlink_refused(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "workspace").mkdir()
            a = root / "text"
            a.write_bytes(mod.GITCRYPT_MAGIC + b"private")
            (root / "workspace/HEARTBEAT.md").symlink_to(a)
            result = mod.inventory(root)
            record = next(x for x in result["known_files"] if x["role"] == "workspace/HEARTBEAT.md")
            self.assertEqual(record["source_status"], "unsafe_type_or_owner")

if __name__ == "__main__":
    unittest.main()
