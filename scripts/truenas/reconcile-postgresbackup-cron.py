#!/usr/bin/env python3
"""Reconcile the native TrueNAS cron jobs that run apps/postgresbackup.

Three owned jobs: the daily wave (BACKUP_DATABASES of the Compose, 14 days),
and the Sentry archives, monthly (kept 12 months) and yearly (kept 3 years).
Sentry is out of the daily wave on purpose: its nodestore is large.

--check is offline and prints the contracts. --apply registers missing jobs
DISABLED (nothing runs yet). --enable needs POSTGRES_BACKUP_CRON_APPROVED=YES
after a reviewed manual run and a restore test; --disable stops the schedules.
--job limits --apply/--enable/--disable to one job. An existing job with a
different contract is refused, never overwritten.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess

NAME = "nabla-postgresbackup"
RESTORE_RECEIPT = Path('/mnt/cpool/secrets/runtime/postgresbackup/restore-acceptance.json')
BACKUP_ROOT = Path('/mnt/cpool/backup/postgres')
RESTORE_EVIDENCE_MAX_AGE = timedelta(days=7)
CHECKOUT = Path("/mnt/cpool/compose/nabla-compose")
APP_DIR = CHECKOUT / "apps" / "postgresbackup"
BASE_COMMAND = (
    "/usr/bin/docker compose "
    f"--project-directory {APP_DIR} "
    f"--file {APP_DIR / 'compose.yml'} "
    "--profile manual run --rm --no-deps"
)


def job(name: str, schedule: dict[str, str], overrides: str = "") -> dict:
    return {
        "description": name,
        "user": "root",
        "enabled": False,
        "stdout": True,
        "stderr": True,
        "schedule": {"minute": "20", "hour": "03", "dom": "*", "month": "*", "dow": "*", **schedule},
        "command": f"{BASE_COMMAND}{overrides} postgresbackup",
    }


def sentry_archive(series: str, keep_days: int) -> str:
    return (f" -e BACKUP_DATABASES=sentry -e BACKUP_SERIES={series}"
            f" -e BACKUP_KEEP_DAYS={keep_days} -e BACKUP_REQUIRE_ALL=true")


# Archives start at 04:20, after the daily wave, to avoid two dumps at once.
JOBS = {
    "daily": job(NAME, {}),
    "sentry-monthly": job(f"{NAME}-sentry-monthly", {"minute": "20", "hour": "04", "dom": "1"},
                          sentry_archive("monthly", 370)),
    "sentry-yearly": job(f"{NAME}-sentry-yearly", {"minute": "20", "hour": "05", "dom": "2", "month": "1"},
                         sentry_archive("yearly", 1100)),
}
JOB = JOBS["daily"]


def middleware(method: str, *arguments: object) -> object:
    argv = ["midclt", "call", method, *(json.dumps(value) for value in arguments)]
    result = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=20)
    if result.returncode:
        raise RuntimeError("TrueNAS cron middleware operation failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("TrueNAS cron middleware returned invalid JSON") from exc


def existing_job(spec: dict) -> dict | None:
    records = middleware("cronjob.query")
    if not isinstance(records, list):
        raise RuntimeError("cronjob.query returned non-array")
    matches = [entry for entry in records
               if isinstance(entry, dict) and entry.get("description") == spec["description"]]
    if len(matches) > 1:
        raise RuntimeError("duplicate owned Cron jobs; reconcile manually")
    return matches[0] if matches else None


def same_contract(entry: dict, spec: dict) -> bool:
    return all(entry.get(key) == spec[key] for key in ("description", "user", "command", "schedule"))


def require_environment() -> None:
    if os.geteuid() != 0 or CHECKOUT.is_symlink() or not CHECKOUT.is_dir():
        raise RuntimeError("must run as root on canonical TrueNAS checkout")
    if not (APP_DIR / "compose.yml").is_file() or not (APP_DIR / "backup.sh").is_file():
        raise RuntimeError("apps/postgresbackup is incomplete in the canonical checkout")


def reconcile(spec: dict, args: argparse.Namespace) -> None:
    label = spec["description"]
    old = existing_job(spec)
    if old is not None and not same_contract(old, spec):
        raise RuntimeError(f"{label}: existing owned cron configuration drift: refuse mutation")
    if args.apply:
        if old:
            print(f"EXISTS: {label} left unchanged")
            return
        middleware("cronjob.create", spec)
        print(f"CREATED: {label} disabled (no backup started)")
        return
    if old is None:
        raise RuntimeError(f"{label}: register the disabled native Cron job with --apply first")
    identifier = old.get("id")
    if not isinstance(identifier, int) or identifier <= 0:
        raise RuntimeError(f"{label}: owned TrueNAS cron has no valid numeric ID")
    middleware("cronjob.update", identifier, {"enabled": bool(args.enable)})
    print(f"UPDATED: {label} " + ("enabled" if args.enable else "disabled"))



def audit_live(selected: list[dict]) -> None:
    """Compare the live middleware records, not the desired config alone."""
    records = middleware("cronjob.query")
    if not isinstance(records, list):
        raise RuntimeError("cronjob.query returned non-array")
    issues = []
    for spec in selected:
        matches = [item for item in records if isinstance(item, dict)
                   and item.get("description") == spec["description"]]
        if len(matches) != 1:
            issues.append(f"{spec['description']}: expected one live cron job, got {len(matches)}")
            continue
        entry = matches[0]
        if type(entry.get("enabled")) is not bool:
            issues.append(f"{spec['description']}: live cron enabled state missing or invalid")
            enabled_label = "UNKNOWN"
        else:
            enabled_label = "true" if entry["enabled"] else "false"
        if not same_contract(entry, spec):
            issues.append(f"{spec['description']}: live cron contract drift")
        print(f"LIVE: {spec['description']} enabled={enabled_label} "
              f"contract={'MATCH' if same_contract(entry, spec) else 'DRIFT'}")
    if issues:
        raise RuntimeError("; ".join(issues))


def validate_restore_receipt(path: Path = RESTORE_RECEIPT, *,
                             backup_root: Path = BACKUP_ROOT,
                             expected_uid: int = 0,
                             now: datetime | None = None) -> dict:
    """Require a private, fresh, checksum-matched independent restore receipt."""
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("restore_receipt_missing_or_symlink")
    metadata = path.stat()
    parent = path.parent.stat()
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != expected_uid
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or parent.st_uid != expected_uid or parent.st_mode & 0o077):
        raise RuntimeError("restore_receipt_permissions_invalid")
    try:
        receipt = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(receipt, dict):
            raise ValueError("expected an object")
        if receipt.get("schema") != 1 or receipt.get("state") != "ISOLATED_RESTORE_VERIFIED":
            raise ValueError("unexpected status")
        count = receipt.get("restored_relations")
        if type(count) is not int or count < 1:
            raise ValueError("no restored objects")
        timestamp = datetime.fromisoformat(receipt["checked_at"])
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must have timezone")
        age = (now or datetime.now(timezone.utc)) - timestamp.astimezone(timezone.utc)
        if age < timedelta(minutes=-5) or age > RESTORE_EVIDENCE_MAX_AGE:
            raise ValueError("stale or future receipt")
        verifier_file = Path(__file__).with_name("verify-postgresbackup-restore.py")
        spec = importlib.util.spec_from_file_location("postgresbackup_restore_check", verifier_file)
        if spec is None or spec.loader is None:
            raise ValueError("restore verifier unavailable")
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        archive = Path(receipt["archive"])
        database, digest = verifier.verify_archive(archive, backup_root)
        if (receipt.get("database") != database or receipt.get("sha256") != digest
                or receipt.get("image") != verifier.POSTGRES_IMAGE):
            raise ValueError("archive receipt mismatch")
        if database == "sentry":
            raise ValueError("Sentry series requires separate restoration evidence")
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("restore_receipt_not_verified") from exc
    return receipt

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="offline desired-state contract only")
    mode.add_argument("--check-live", action="store_true", help="read the actual TrueNAS cron state")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--enable", action="store_true")
    mode.add_argument("--disable", action="store_true")
    parser.add_argument("--job", choices=sorted(JOBS), help="limit the mutation to one job")
    args = parser.parse_args()
    selected = [JOBS[args.job]] if args.job else list(JOBS.values())
    if args.check:
        for spec in selected:
            when = spec["schedule"]
            print(f"CHECK: {spec['description']}: {when['minute']} {when['hour']} {when['dom']} "
                  f"{when['month']} {when['dow']} (appliance time); desired disabled; live NOT_CHECKED")
            print(f"CHECK: command = {spec['command']}")
        print("CHECK: no container started, no cron mutated")
        return 0
    require_environment()
    if args.check_live:
        audit_live(selected)
        return 0
    if args.enable and os.environ.get("POSTGRES_BACKUP_CRON_APPROVED") != "YES":
        raise RuntimeError("explicit POSTGRES_BACKUP_CRON_APPROVED=YES required (after a manual run and a restore test)")
    if args.enable:
        if args.job != "daily":
            raise RuntimeError("enable daily job explicitly; Sentry archives require separate proof")
        validate_restore_receipt()
    for spec in selected:
        reconcile(spec, args)
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"REJECTED: {exc}") from None
