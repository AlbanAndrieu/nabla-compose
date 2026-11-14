#!/usr/bin/env python3
"""Verify a postgresbackup archive and restore it in a disposable offline container.

No production database is touched. The Docker image must exist locally: pulls,
ports, network access, retention changes and cron activation are prohibited.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import tempfile
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKUP_ROOT = Path('/mnt/cpool/backup/postgres')
POSTGRES_IMAGE = ('postgres:18.6-trixie@sha256:'
                  'edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6')
RECEIPT_FILE = Path('/mnt/cpool/secrets/runtime/postgresbackup/restore-acceptance.json')
NAME_RE = re.compile(r'^([a-z][a-z0-9_]{0,62})-\d{8}T\d{6}Z\.dump$')


def verify_archive(archive: Path, root: Path = BACKUP_ROOT) -> tuple[str, str]:
    """Validate canonical location and exact sidecar, then hash archive."""
    root = root.resolve(strict=True)
    if archive.is_symlink() or not archive.is_file():
        raise ValueError('archive_missing_or_symlink')
    resolved = archive.resolve(strict=True)
    match = NAME_RE.fullmatch(archive.name)
    if not match or resolved.parent != root / match.group(1):
        raise ValueError('archive_outside_canonical_database_directory')
    sidecar = Path(f'{archive}.sha256')
    if sidecar.is_symlink() or not sidecar.is_file():
        raise ValueError('checksum_missing_or_symlink')
    raw = sidecar.read_text(encoding='ascii')
    checksum_line = re.fullmatch(r'([0-9a-f]{64})  ([a-z][a-z0-9_]{0,62}-\d{8}T\d{6}Z\.dump)\n?', raw)
    if checksum_line is None or checksum_line.group(2) != archive.name:
        raise ValueError('checksum_sidecar_invalid')
    digest = hashlib.sha256()
    with archive.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    actual = digest.hexdigest()
    if not hmac.compare_digest(checksum_line.group(1), actual):
        raise ValueError('archive_checksum_mismatch')
    return match.group(1), actual


def run(command: list[str], *, timeout: int = 90, stdin=None) -> str:
    """Never disclose subprocess output: tools can include SQL or credentials."""
    try:
        result = subprocess.run(command, stdin=stdin, capture_output=True,
                                check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f'command_unavailable_or_timeout:{command[0]}') from exc
    if result.returncode:
        raise RuntimeError(f'command_failed:{command[0]}:exit_{result.returncode}')
    return result.stdout.decode('utf-8', errors='replace').strip()


def test_restore(archive: Path, timeout: int) -> int:
    if shutil.which('docker') is None:
        raise RuntimeError('docker_unavailable')
    run(['docker', 'image', 'inspect', POSTGRES_IMAGE])
    # The image cannot be fetched: this operation stays offline.
    with archive.open('rb') as stream:
        run(['docker', 'run', '--rm', '-i', '--pull', 'never', '--network', 'none',
             '--entrypoint', 'pg_restore', POSTGRES_IMAGE, '--list', '-'],
            stdin=stream, timeout=timeout)
    name = f'nabla-pg-restore-{uuid.uuid4().hex[:12]}'
    started = False
    try:
        run(['docker', 'run', '-d', '--rm', '--pull', 'never', '--network', 'none',
             '--security-opt', 'no-new-privileges:true', '--name', name,
             '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', POSTGRES_IMAGE,
             '-c', 'listen_addresses='], timeout=60)
        started = True
        for attempt in range(60):
            try:
                run(['docker', 'exec', name, 'pg_isready', '-q', '-U', 'postgres'],
                    timeout=5)
                break
            except RuntimeError:
                if attempt == 59:
                    raise RuntimeError('isolated_postgres_not_ready') from None
                time.sleep(1)
        run(['docker', 'exec', '-u', 'postgres', name, 'createdb',
             '-U', 'postgres', '-T', 'template0', 'restore_validation'])
        with archive.open('rb') as stream:
            run(['docker', 'exec', '-i', '-u', 'postgres', name, 'pg_restore',
                 '--exit-on-error', '--no-owner', '--no-acl', '-U', 'postgres',
                 '-d', 'restore_validation'], stdin=stream, timeout=timeout)
        count = run(['docker', 'exec', '-u', 'postgres', name, 'psql', '-U', 'postgres',
                     '-d', 'restore_validation', '-Atc',
                     "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                     "WHERE n.nspname NOT IN ('pg_catalog','information_schema') "
                     "AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','v','m','S')"])
        if not count.isdecimal():
            raise RuntimeError('invalid_restored_object_count')
        if int(count) == 0:
            raise RuntimeError('empty_restored_database')
        return int(count)
    finally:
        if started:
            # No output from a failed container is copied to a public log.
            subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=30, check=False)



def write_restore_receipt(payload: dict[str, object], path: Path = RECEIPT_FILE) -> None:
    """Atomically write root-owned technical evidence; never claim business acceptance."""
    if os.geteuid() != 0:
        raise RuntimeError('restore_receipt_requires_root')
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise RuntimeError('restore_receipt_directory_missing')
    meta = parent.stat()
    if meta.st_uid != 0 or meta.st_mode & 0o077:
        raise RuntimeError('restore_receipt_directory_not_private')
    if path.is_symlink():
        raise RuntimeError('restore_receipt_symlink_rejected')
    fd, name = tempfile.mkstemp(dir=parent, prefix='.restore-evidence-', suffix='.tmp')
    temporary = Path(name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='checksum only; NOT a restore test')
    mode.add_argument('--restore-test', action='store_true', help='offline isolated Docker restore')
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--write-receipt', action='store_true',
                        help='write root-only technical restore evidence after a successful restore')
    args = parser.parse_args(argv)
    if args.write_receipt and not args.restore_test:
        parser.error('--write-receipt requires --restore-test')
    if not 60 <= args.timeout <= 7200:
        parser.error('--timeout must be between 60 and 7200 seconds')
    try:
        database, digest = verify_archive(args.archive)
        output = {'database': database, 'sha256': digest,
                  'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  'state': 'ARCHIVE_CHECKSUM_VERIFIED'}
        if args.restore_test:
            output['restored_relations'] = test_restore(args.archive, args.timeout)
            output['state'] = 'ISOLATED_RESTORE_VERIFIED'
            if args.write_receipt:
                write_restore_receipt({**output, 'schema': 1,
                                       'archive': str(args.archive.resolve(strict=True)),
                                       'image': POSTGRES_IMAGE})
        print(json.dumps(output, sort_keys=True))
        return 0
    except (ValueError, RuntimeError, OSError, UnicodeError) as exc:
        print(json.dumps({'state': 'NOT_VERIFIED', 'reason': str(exc).split(':', 1)[0]}),
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
