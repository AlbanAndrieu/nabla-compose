"""Offline, stdlib-only acceptance contracts for postgresbackup restore verification."""
from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/truenas/verify-postgresbackup-restore.py'
spec = importlib.util.spec_from_file_location('restore_verifier', SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class RestoreContract(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix='pg-restore-contract-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'fastapisample'
        self.folder.mkdir()
        self.archive = self.folder / 'fastapisample-20261113T010203Z.dump'
        self.archive.write_bytes(b'fixture-data-not-a-real-backup')
        self.digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.sidecar = Path(f'{self.archive}.sha256')
        self.sidecar.write_text(f'{self.digest}  {self.archive.name}\n', encoding='ascii')

    def test_exact_checksum_and_canonical_path(self) -> None:
        self.assertEqual(module.verify_archive(self.archive, self.root),
                         ('fastapisample', self.digest))

    def test_checksum_tampering_rejected(self) -> None:
        self.archive.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum_mismatch'):
            module.verify_archive(self.archive, self.root)

    def test_redirected_checksum_file_rejected(self) -> None:
        self.sidecar.unlink()
        self.sidecar.symlink_to(self.archive)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            module.verify_archive(self.archive, self.root)

    def test_sidecar_cannot_redirect_to_other_file(self) -> None:
        self.sidecar.write_text(f'{self.digest}  ../other.dump\n', encoding='ascii')
        with self.assertRaisesRegex(ValueError, 'sidecar_invalid'):
            module.verify_archive(self.archive, self.root)

    def test_archive_outside_database_directory_rejected(self) -> None:
        other = self.root / self.archive.name
        other.write_bytes(self.archive.read_bytes())
        Path(f'{other}.sha256').write_text(f'{self.digest}  {other.name}\n', encoding='ascii')
        with self.assertRaisesRegex(ValueError, 'outside_canonical'):
            module.verify_archive(other, self.root)

    def test_restore_never_runs_without_local_docker(self) -> None:
        with patch.object(module.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'docker_unavailable'):
                module.test_restore(self.archive, 60)

    def test_failing_process_error_discards_sql_content(self) -> None:
        failed = subprocess.CompletedProcess([], 1, b'', b'PRIVATE_SECRET_TOKEN')
        with patch.object(module.subprocess, 'run', return_value=failed):
            with self.assertRaisesRegex(RuntimeError, 'command_failed') as error:
                module.run(['fake'])
        self.assertNotIn('PRIVATE_SECRET_TOKEN', str(error.exception))

    def test_help_does_not_trigger_docker(self) -> None:
        result = subprocess.run([sys.executable, str(SCRIPT), '--help'],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--restore-test', result.stdout)


if __name__ == '__main__':
    unittest.main()
