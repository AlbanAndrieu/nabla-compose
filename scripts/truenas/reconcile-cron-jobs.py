#!/usr/bin/env python3
"""Declare the native TrueNAS cron jobs and how every job reports.

Every job runs through cron-notify.sh with stdout and stderr hidden: TrueNAS
mails nothing, and only a failure sends a short summary to OpenClaw (mail and
Slack). This script owns the jobs below, moved on 26/11/2026 from
ansible-workstation playbooks/truenas-stabilize.yml and from the TrueNAS UI.
The night-window, postgresbackup and DefectDojo reconcilers still create and
enable their own jobs; --apply only aligns how those report.

--check is offline. --apply runs as root on TrueNAS: it creates the missing
owned jobs, updates drifted ones (never their `enabled` flag), and deletes the
retired ones.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess

CHECKOUT = Path("/mnt/cpool/compose/nabla-compose")
REPO = Path(__file__).resolve().parents[2]
SCRIPTS = CHECKOUT / "scripts"
NOTIFY = f"bash {SCRIPTS}/truenas/cron-notify.sh"
REPORTING = ("command", "stdout", "stderr")
OWNED_FIELDS = ("description", "user", "schedule", *REPORTING)


def notified(name: str, command: str) -> str:
    return f"{NOTIFY} {name} -- {command}"


def job(name: str, command: str, schedule: dict[str, str], user: str = "root", adopt: str = "") -> dict:
    """`adopt` matches a job created by hand under another description, by command."""
    return {
        "description": name,
        "user": user,
        "enabled": True,
        "stdout": True,
        "stderr": True,
        "schedule": {"minute": "0", "hour": "*", "dom": "*", "month": "*", "dow": "*", **schedule},
        "command": notified(name, command),
        "adopt": adopt,
    }


# One long test per disk and week of the month; a WD30EFRX long test takes about 7 h.
# 08:00, after the 01:00-07:00 night window: one disk under test slows every raidz2 read.
SMART = {
    "sda": ("ata-WDC_WD30EFRX-68AX9N0_WD-WMC1T3457796", "7"),
    "sdb": ("ata-WDC_WD30EFRX-68EUZN0_WD-WX32FK2NSIGF", "14"),
    "sdc": ("ata-WDC_WD30EFRX-68EUZN0_WD-WCA2F74L52TH", "21"),
    "sdd": ("ata-WDC_WD30EFRX-68AX9N0_WD-WMC1T3491311", "28"),
}

OWNED = [
    job("nabla-hourly-sync", f"bash {SCRIPTS}/cron.sh {CHECKOUT}", {}, user="albandrieu", adopt="scripts/cron.sh"),
    # 01:30, inside the night window of clamav; clamav-scan.sh starts the App otherwise.
    job("clamav-scan", f"bash {SCRIPTS}/truenas/clamav-scan.sh full", {"minute": "30", "hour": "1", "dom": "1"}),
    job("clamav-scan-exposed", f"bash {SCRIPTS}/truenas/clamav-scan.sh exposed",
        {"minute": "30", "hour": "1", "dow": "6"}),
    job("nabla-docker-image-prune",
        f"env NABLA_DOCKER_IMAGE_PRUNE_MIN_AGE_HOURS=168 bash {SCRIPTS}/truenas/prune-docker-images.sh --apply",
        {"minute": "37", "hour": "4", "dow": "0"}, adopt="prune-docker-images.sh"),
    *(job(f"smart-long-{disk}", f"smartctl -t long /dev/disk/by-id/{device}", {"hour": "8", "dom": dom})
      for disk, (device, dom) in SMART.items()),
]
# clamav-scan.sh prunes the scan logs older than 90 days after each scan.
RETIRED = ("clamav-cleanup",)


def load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), REPO / "scripts/truenas" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def borrowed() -> list[dict]:
    """Jobs other reconcilers create; only their reporting is aligned here."""
    return [
        *load("reconcile-night-window-cron").JOBS,
        *load("reconcile-postgresbackup-cron").JOBS.values(),
        load("reconcile-defectdojo-artifact-cron").JOB,
    ]


def middleware(method: str, *arguments: object) -> object:
    argv = ["midclt", "call", method, *(json.dumps(v) for v in arguments)]
    result = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=60)
    if result.returncode:
        raise RuntimeError(f"TrueNAS middleware {method} failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"TrueNAS middleware {method} returned invalid JSON") from exc


def align(row: dict, spec: dict, fields: tuple[str, ...]) -> str:
    diff = {key: spec[key] for key in fields if row.get(key) != spec[key]}
    if not diff:
        return "OK"
    middleware("cronjob.update", row["id"], diff)
    return f"UPDATED ({', '.join(diff)})"


def apply() -> None:
    records = middleware("cronjob.query")
    if not isinstance(records, list):
        raise RuntimeError("cronjob.query returned non-array")
    for spec in OWNED:
        matches = [r for r in records if r.get("description") == spec["description"]]
        if not matches and spec["adopt"]:
            matches = [r for r in records if spec["adopt"] in (r.get("command") or "")]
        if len(matches) > 1:
            raise RuntimeError(f"several cron jobs match {spec['description']}; reconcile manually")
        if not matches:
            middleware("cronjob.create", {k: v for k, v in spec.items() if k != "adopt"})
            print(f"CREATED: {spec['description']}")
            continue
        print(f"{align(matches[0], spec, OWNED_FIELDS)}: {spec['description']}")
    for spec in borrowed():
        matches = [r for r in records if r.get("description") == spec["description"]]
        if not matches:
            print(f"ABSENT: {spec['description']} (its own reconciler creates it)")
            continue
        print(f"{align(matches[0], spec, REPORTING)}: {spec['description']}")
    for name in RETIRED:
        for row in (r for r in records if r.get("description") == name):
            middleware("cronjob.delete", row["id"])
            print(f"DELETED: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.check:
        for spec in OWNED:
            s = spec["schedule"]
            print(f"OWNED: {spec['description']} {s['minute']} {s['hour']} {s['dom']} * {s['dow']} "
                  f"({spec['user']}) :: {spec['command']}")
        for spec in borrowed():
            print(f"REPORTING: {spec['description']} :: {spec['command']}")
        print(f"RETIRED: {' '.join(RETIRED)}")
        return 0
    if os.geteuid() != 0 or CHECKOUT.is_symlink() or not (CHECKOUT / "scripts/truenas/cron-notify.sh").is_file():
        raise RuntimeError("run as root on the canonical TrueNAS checkout that holds cron-notify.sh")
    apply()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"REJECTED: {exc}") from None
