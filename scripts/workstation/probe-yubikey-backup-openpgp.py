#!/usr/bin/env python3
"""Optional supervised, public OpenPGP transport probe of the backup YubiKey.

--check is host-only. --probe may start scdaemon and query public card status;
never signs, decrypts, moves keys, asks PIN, or prints GPG card metadata.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys

SERIAL = '22916048'
ACK = 'QUERY_OPENPGP_BACKUP_22916048'


def check() -> str:
    if not shutil.which('gpg') or not shutil.which('ykman'):
        return 'TOOLS_MISSING'
    return 'TOOLS_PRESENT_HARDWARE_NOT_CHECKED'


def probe(tty: bool) -> str:
    if check() != 'TOOLS_PRESENT_HARDWARE_NOT_CHECKED':
        return 'TOOLS_MISSING'
    if not tty:
        return 'INTERACTIVE_TERMINAL_REQUIRED'
    try:
        visible = subprocess.run(['ykman', 'list', '--serials'],
                                 stdin=subprocess.DEVNULL, capture_output=True,
                                 text=True, timeout=12, check=False)
        if visible.returncode or visible.stderr.strip() or visible.stdout.splitlines() != [SERIAL]:
            return 'EXPECTED_ONE_BACKUP_YUBIKEY'
        # May autostart scdaemon: intentionally NOT called from passive checks.
        result = subprocess.run(['gpg', '--batch', '--no-tty', '--card-status'],
                                stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=20, check=False)
        if result.returncode or result.stderr.strip():
            return 'OPENPGP_TRANSPORT_NOT_CONFIRMED'
        if len(result.stdout) > 32768 or '\x00' in result.stdout:
            return 'OPENPGP_TRANSPORT_NOT_CONFIRMED'
        return 'GPG_CARD_STATUS_RESPONDS_PUBLIC_ONLY_IDENTITY_UNVERIFIED'
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        return 'OPENPGP_TRANSPORT_NOT_CONFIRMED'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    opt = parser.add_mutually_exclusive_group(required=True)
    opt.add_argument('--check', action='store_true')
    opt.add_argument('--probe', action='store_true')
    parser.add_argument('--acknowledge')
    args = parser.parse_args(argv)
    if args.check and args.acknowledge:
        parser.error('acknowledgment is only accepted for --probe')
    if args.probe and args.acknowledge != ACK:
        parser.error('explicit backup OpenPGP probe acknowledgment required')
    state = check() if args.check else probe(sys.stdin.isatty() and sys.stdout.isatty())
    print(json.dumps({'state': state, 'serial': SERIAL, 'status': 'NO-GO',
                      'card_private_key_tested': False,
                      'signature_verified': False,
                      'hardware_mutation_authorized': False}, sort_keys=True))
    return 0 if state in ('TOOLS_PRESENT_HARDWARE_NOT_CHECKED',
                           'GPG_CARD_STATUS_RESPONDS_PUBLIC_ONLY_IDENTITY_UNVERIFIED') else 3


if __name__ == '__main__':
    sys.exit(main())
