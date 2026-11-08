#!/usr/bin/env python3
"""Reconcile the native TrueNAS cron job that runs apps/postgres-backup.

--check is offline and prints the contract. --apply registers the job
DISABLED (nothing runs yet). --enable needs POSTGRES_BACKUP_CRON_APPROVED=YES
after a reviewed manual run and a restore test; --disable stops the schedule.
An existing job with a different contract is refused, never overwritten.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

NAME = "nabla-postgres-backup"
CHECKOUT = Path("/mnt/cpool/compose/nabla-compose")
APP_DIR = CHECKOUT / "apps" / "postgres-backup"
JOB = {
    "description": NAME,
    "user": "root",
    "enabled": False,
    "stdout": True,
    "stderr": True,
    "schedule": {
        "minute": "20",
        "hour": "03",
        "dom": "*",
        "month": "*",
        "dow": "*",
    },
    "command": (
        "/usr/bin/docker compose "
        f"--project-directory {APP_DIR} "
        f"--file {APP_DIR / 'compose.yml'} "
        "--profile manual run --rm --no-deps postgres-backup"
    ),
}


def middleware(method: str, *arguments: object) -> object:
    argv = ["midclt", "call", method, *(json.dumps(value) for value in arguments)]
    result = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=20)
    if result.returncode:
        raise RuntimeError("TrueNAS cron middleware operation failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("TrueNAS cron middleware returned invalid JSON") from exc


def existing_job() -> dict | None:
    records = middleware("cronjob.query")
    if not isinstance(records, list):
        raise RuntimeError("cronjob.query returned non-array")
    matches = [entry for entry in records if isinstance(entry, dict) and entry.get("description") == NAME]
    if len(matches) > 1:
        raise RuntimeError("duplicate owned Cron jobs; reconcile manually")
    return matches[0] if matches else None


def same_contract(entry: dict) -> bool:
    return all(entry.get(key) == JOB[key] for key in ("description", "user", "command", "schedule"))


def require_environment() -> None:
    if os.geteuid() != 0 or CHECKOUT.is_symlink() or not CHECKOUT.is_dir():
        raise RuntimeError("must run as root on canonical TrueNAS checkout")
    if not (APP_DIR / "compose.yml").is_file() or not (APP_DIR / "backup.sh").is_file():
        raise RuntimeError("apps/postgres-backup is incomplete in the canonical checkout")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--enable", action="store_true")
    mode.add_argument("--disable", action="store_true")
    args = parser.parse_args()
    if args.check:
        print("CHECK: native TrueNAS cron, daily 03:20 appliance time; registered disabled")
        print(f"CHECK: command = {JOB['command']}")
        print("CHECK: no container started, no cron mutated")
        return 0
    require_environment()
    old = existing_job()
    if old is not None and not same_contract(old):
        raise RuntimeError("existing owned cron configuration drift: refuse mutation")
    if args.apply:
        if old:
            print("EXISTS: native TrueNAS postgres-backup cron left unchanged")
            return 0
        middleware("cronjob.create", JOB)
        print("CREATED: disabled native TrueNAS Cron job (no backup started)")
        return 0
    if old is None:
        raise RuntimeError("register the disabled native Cron job with --apply first")
    identifier = old.get("id")
    if not isinstance(identifier, int) or identifier <= 0:
        raise RuntimeError("owned TrueNAS cron has no valid numeric ID")
    if args.enable and os.environ.get("POSTGRES_BACKUP_CRON_APPROVED") != "YES":
        raise RuntimeError("explicit POSTGRES_BACKUP_CRON_APPROVED=YES required (after a manual run and a restore test)")
    middleware("cronjob.update", identifier, {"enabled": bool(args.enable)})
    print("UPDATED: native TrueNAS cron " + ("enabled" if args.enable else "disabled"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"REJECTED: {exc}") from None
