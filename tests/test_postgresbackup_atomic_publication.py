"""Local acceptance of immutable archive publication with fake PostgreSQL clients."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / 'apps/postgresbackup/backup.sh'
STAMP = '20261114T010203Z'


class AtomicArchiveTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.data = self.root / 'data'
        self.data.mkdir()
        scripts = {
            'psql': '#!/bin/sh\necho 1\n',
            'pg_dump': '#!/bin/sh\nfor x do case "$x" in --file=*) printf PGDMP-test > "${x#--file=}" ;; esac; done\n',
            'pg_restore': '#!/bin/sh\nexit 0\n',
            'date': f'#!/bin/sh\necho {STAMP}\n',
        }
        for name, body in scripts.items():
            item = self.bin / name
            item.write_text(body)
            item.chmod(0o755)
        self.archive = self.data / 'fastapisample' / f'fastapisample-{STAMP}.dump'
        self.env = {**os.environ, 'PATH': f'{self.bin}:{os.environ["PATH"]}',
                    'POSTGRES_HOST': 'localhost', 'POSTGRES_USER': 'pgbackup',
                    'POSTGRES_PASSWORD': 'fixture-test-secret',
                    'BACKUP_DATABASES': 'fastapisample', 'BACKUP_DIR': str(self.data)}

    def run_job(self):
        return subprocess.run(['bash', str(BACKUP)], env=self.env, text=True,
                              capture_output=True, timeout=10)

    def test_creates_a_valid_sidecar_without_including_secrets(self):
        result = self.run_job()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.archive.read_bytes(), b'PGDMP-test')
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.assertEqual(Path(str(self.archive) + '.sha256').read_text(),
                         f'{digest}  {self.archive.name}\n')
        self.assertNotIn('fixture-test-secret', result.stdout + result.stderr)
        self.assertEqual(self.archive.stat().st_mode & 0o777, 0o600)

    def test_same_second_collision_refuses_overwrite(self):
        result = self.run_job()
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = self.archive.read_bytes()
        checksum = Path(str(self.archive) + '.sha256').read_bytes()
        second = self.run_job()
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(self.archive.read_bytes(), saved)
        self.assertEqual(Path(str(self.archive) + '.sha256').read_bytes(), checksum)
        self.assertIn('already exists', second.stderr)

    def test_existing_sidecar_causes_archive_rollback(self):
        self.archive.parent.mkdir(parents=True)
        sidecar = Path(str(self.archive) + '.sha256')
        sidecar.write_text('existing-sidecar-should-not-be-replaced')
        result = self.run_job()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.archive.exists())
        self.assertEqual(sidecar.read_text(), 'existing-sidecar-should-not-be-replaced')
        self.assertFalse((self.data / '.last-success.json').exists())


if __name__ == '__main__':
    unittest.main()
