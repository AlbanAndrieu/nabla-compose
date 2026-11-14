"""Offline regression tests for the TrueNAS PostgreSQL cron acceptance gate."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/reconcile-postgresbackup-cron.py"
spec = importlib.util.spec_from_file_location("postgresbackup_cron_gate", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CronAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / "fastapisample"
        self.folder.mkdir()
        self.archive = self.folder / "fastapisample-20261114T030000Z.dump"
        self.archive.write_bytes(b"test-data")
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        Path(str(self.archive) + ".sha256").write_text(
            f"{digest}  {self.archive.name}\n", encoding="ascii"
        )
        self.receipt = self.root / "receipt.json"
        self.payload = {
            "schema": 1,
            "state": "ISOLATED_RESTORE_VERIFIED",
            "database": "fastapisample",
            "archive": str(self.archive),
            "sha256": digest,
            "restored_relations": 3,
            "image": module_restorer_image(),
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.write_payload(self.payload)

    def write_payload(self, data):
        self.receipt.write_text(json.dumps(data), encoding="utf-8")
        self.receipt.chmod(0o600)

    def verify(self, **kwargs):
        return module.validate_restore_receipt(
            self.receipt, backup_root=self.root, expected_uid=os.getuid(), **kwargs
        )

    def test_valid_receipt_matches_real_archive_checksum(self):
        self.assertEqual(self.verify()["restored_relations"], 3)

    def test_stale_receipt_is_rejected(self):
        payload = {**self.payload,
                   "checked_at": (datetime.now(timezone.utc) - timedelta(days=9)).isoformat()}
        self.write_payload(payload)
        with self.assertRaisesRegex(RuntimeError, "not_verified"):
            self.verify()

    def test_zero_relations_is_rejected(self):
        self.write_payload({**self.payload, "restored_relations": 0})
        with self.assertRaisesRegex(RuntimeError, "not_verified"):
            self.verify()

    def test_archive_tampering_is_rejected(self):
        self.archive.write_bytes(b"modified")
        with self.assertRaisesRegex(RuntimeError, "not_verified"):
            self.verify()

    def test_receipt_permissions_and_symlinks_rejected(self):
        self.receipt.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, "permissions_invalid"):
            self.verify()
        self.receipt.unlink()
        self.receipt.symlink_to(self.archive)
        with self.assertRaisesRegex(RuntimeError, "missing_or_symlink"):
            self.verify()

    def test_live_status_detects_disabled_running_and_drift(self):
        specs = [module.JOBS["daily"]]
        item = {**module.JOB, "id": 5, "enabled": True}
        with patch.object(module, "middleware", return_value=[item]):
            module.audit_live(specs)
        with patch.object(module, "middleware", return_value=[{**item, "enabled": False}]):
            module.audit_live(specs)
        with patch.object(module, "middleware", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "expected one live cron"):
                module.audit_live(specs)
        with patch.object(module, "middleware", return_value=[{**item, "command": "changed"}]):
            with self.assertRaisesRegex(RuntimeError, "contract drift"):
                module.audit_live(specs)


    def test_enable_fails_before_middleware_without_receipt(self):
        with patch.object(module, "require_environment"), \
             patch.object(module, "validate_restore_receipt",
                          side_effect=RuntimeError("restore_receipt_missing_or_symlink")), \
             patch.object(module, "middleware") as middleware, \
             patch("sys.argv", ["cron", "--enable", "--job", "daily"]), \
             patch.dict(os.environ, {"POSTGRES_BACKUP_CRON_APPROVED": "YES"}):
            with self.assertRaisesRegex(RuntimeError, "restore_receipt_missing"):
                module.main()
            middleware.assert_not_called()

    def test_enable_requires_explicit_daily_selection(self):
        with patch.object(module, "require_environment"), \
             patch.object(module, "validate_restore_receipt") as verify, \
             patch.object(module, "middleware") as middleware, \
             patch("sys.argv", ["cron", "--enable"]), \
             patch.dict(os.environ, {"POSTGRES_BACKUP_CRON_APPROVED": "YES"}):
            with self.assertRaisesRegex(RuntimeError, "enable daily job explicitly"):
                module.main()
            verify.assert_not_called()
            middleware.assert_not_called()

    def test_enable_fails_without_operator_approval(self):
        with patch.object(module, "require_environment"), \
             patch.object(module, "validate_restore_receipt") as verify, \
             patch.object(module, "middleware") as middleware, \
             patch("sys.argv", ["cron", "--enable", "--job", "daily"]), \
             patch.dict(os.environ, {"POSTGRES_BACKUP_CRON_APPROVED": ""}):
            with self.assertRaisesRegex(RuntimeError, "APPROVED=YES required"):
                module.main()
            verify.assert_not_called()
            middleware.assert_not_called()

    def test_receipt_is_never_accepted_for_sentry(self):
        sentry = self.root / "sentry"
        sentry.mkdir()
        archive = sentry / "sentry-20261114T030000Z.dump"
        archive.write_bytes(b"test-sentry")
        sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        Path(str(archive) + ".sha256").write_text(
            f"{sha}  {archive.name}\n", encoding="ascii")
        self.write_payload({**self.payload, "database": "sentry",
                            "sha256": sha, "archive": str(archive)})
        with self.assertRaisesRegex(RuntimeError, "not_verified"):
            self.verify()


def module_restorer_image():
    restore_path = SCRIPT.with_name("verify-postgresbackup-restore.py")
    restore_spec = importlib.util.spec_from_file_location("postgres_restore_image", restore_path)
    assert restore_spec is not None and restore_spec.loader is not None
    restore = importlib.util.module_from_spec(restore_spec)
    restore_spec.loader.exec_module(restore)
    return restore.POSTGRES_IMAGE


if __name__ == "__main__":
    unittest.main()
