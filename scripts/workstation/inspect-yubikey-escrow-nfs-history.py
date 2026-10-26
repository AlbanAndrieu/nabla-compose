#!/usr/bin/env python3
"""Read-only, bounded TrueNAS ZFS snapshot metadata for a missing age escrow.

Reads no encrypted file content. Never reports private basenames, snapshot names,
NFS source details, or SSH diagnostic stderr. No ZFS admin commands are used.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

BASE_SCRIPT = Path(__file__).with_name('inspect-yubikey-escrow-nfs-server.py')
ACK = 'INSPECT_AGE_ESCROW_ZFS_HISTORY_ONLY'
MAX_RESULT_SIZE = 2048
SSH_TARGET = 'albandrieu@172.17.0.24'
ALLOWED_STATES = {'SNAPSHOT_CANDIDATE_FOUND', 'NO_CANDIDATE_IN_CHECKED_SNAPSHOTS',
                  'SNAPSHOT_HISTORY_INCOMPLETE', 'SNAPSHOT_HISTORY_UNAVAILABLE'}
REMOTE_HISTORY = '''import json, os, stat
from pathlib import Path
name = EXPECTED_NAME
# Only these three dataset-level snapshot roots are in scope.
roots = [
    ('/mnt/cpool/backup/lab/.zfs/snapshot', ('secret',)),
    ('/mnt/cpool/backup/.zfs/snapshot', ('lab', 'secret')),
    ('/mnt/cpool/.zfs/snapshot', ('backup', 'lab', 'secret')),
]
seen = 0
found = 0
available = 0
missing = 0
incomplete = False
for root_text, parts in roots:
    directory = Path(root_text)
    try:
        if any(p.is_symlink() for p in (directory, *directory.parents)):
            incomplete = True
            continue
        with os.scandir(directory) as iterator:
            available += 1
            for index, entry in enumerate(iterator):
                if index >= 32:
                    incomplete = True
                    break
                if not entry.is_dir(follow_symlinks=False):
                    continue
                seen += 1
                target = Path(entry.path)
                unsafe = False
                for part in parts:
                    target = target / part
                    try:
                        info = target.lstat()
                        if not stat.S_ISDIR(info.st_mode):
                            unsafe = True
                            break
                    except FileNotFoundError:
                        unsafe = True
                        break
                if unsafe:
                    continue
                candidate = target / name
                try:
                    info = candidate.lstat()
                    if stat.S_ISREG(info.st_mode) and info.st_size > 0:
                        found += 1
                except FileNotFoundError:
                    continue
    except FileNotFoundError:
        missing += 1
    except (PermissionError, OSError):
        incomplete = True
if found:
    state = 'SNAPSHOT_CANDIDATE_FOUND'
elif incomplete:
    state = 'SNAPSHOT_HISTORY_INCOMPLETE'
elif not available:
    state = 'SNAPSHOT_HISTORY_UNAVAILABLE'
else:
    state = 'NO_CANDIDATE_IN_CHECKED_SNAPSHOTS'
print(json.dumps({'state': state, 'snapshots_checked': min(seen, 96),
                  'candidate_copies': min(found, 96),
                  'roots_accessible': available, 'roots_missing': missing},
                 sort_keys=True))
'''
  
def load_base():
    spec = importlib.util.spec_from_file_location('nabla_escrow_nfs_base', BASE_SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError('preflight unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def query_history(ssh_target: str, basename: str) -> dict[str, object]:
    unavailable = {'state': 'SSH_HISTORY_UNAVAILABLE', 'snapshots_checked': None,
                   'candidate_copies': None, 'roots_accessible': None,
                   'roots_missing': None}
    if (not re.fullmatch(r'[a-zA-Z_][a-zA-Z_0-9-]{0,63}@[a-zA-Z0-9][a-zA-Z0-9.:-]{0,200}', ssh_target)
            or not re.fullmatch(r'[A-Za-z0-9_.-]{1,160}\.age', basename)):
        return unavailable
    code = 'EXPECTED_NAME = ' + json.dumps(basename) + '\n' + REMOTE_HISTORY
    command = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
               '-o', 'NumberOfPasswordPrompts=0', '-o', 'ConnectTimeout=5',
               '-o', 'ClearAllForwardings=yes', '--', ssh_target, 'python3', '-']
    try:
        completed = subprocess.run(command, input=code, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   timeout=20, check=False)
        if completed.returncode or len(completed.stdout) > MAX_RESULT_SIZE:
            return unavailable
        result = json.loads(completed.stdout)
        if (not isinstance(result, dict) or
                set(result) != {'state', 'snapshots_checked', 'candidate_copies',
                                'roots_accessible', 'roots_missing'} or
                result['state'] not in ALLOWED_STATES or
                any(type(result[key]) is not int or not 0 <= result[key] <= limit
                    for key, limit in [('snapshots_checked', 96), ('candidate_copies', 96),
                                       ('roots_accessible', 3), ('roots_missing', 3)])):
            return unavailable
        return result
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired):
        return unavailable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    exclusive = parser.add_mutually_exclusive_group(required=True)
    exclusive.add_argument('--check', action='store_true')
    exclusive.add_argument('--probe', action='store_true')
    parser.add_argument('--acknowledge')
    args = parser.parse_args(argv)
    if args.check and args.acknowledge:
        parser.error('no acknowledgment in passive mode')
    if args.probe and args.acknowledge != ACK:
        parser.error('explicit snapshot inventory approval is required')
    mount = 'MOUNT_UNVERIFIED'
    source = 'SOURCE_UNVERIFIED'
    name = None
    result: dict[str, object] = {'state': 'NOT_PROBED', 'snapshots_checked': None,
                                  'candidate_copies': None, 'roots_accessible': None,
                                  'roots_missing': None}
    try:
        base = load_base()
        mount = base.check_mount()
        source, name = base.local_expected_filename(base.LOCAL_SOURCE)
        if args.probe and mount == 'EXPECTED_NFS_EXPORT_MOUNTED' and name:
            result = query_history(SSH_TARGET, name)
    except (OSError, ValueError, ImportError, AttributeError, TypeError):
        pass
    print(json.dumps({'mode': 'AGE_ESCROW_ZFS_SNAPSHOT_METADATA_ONLY',
                      'status': 'NO-GO', 'mount_state': mount, 'source_state': source,
                      **result, 'paths_disclosed': False, 'archive_opened': False,
                      'decryption_attempted': False, 'remote_write_performed': False,
                      'restore_verified': False, 'hardware_mutation_authorized': False},
                     sort_keys=True))
    if args.check:
        return 0 if mount == 'EXPECTED_NFS_EXPORT_MOUNTED' and name else 3
    return 0 if result['state'] in ALLOWED_STATES else 3


if __name__ == '__main__':
    sys.exit(main())
