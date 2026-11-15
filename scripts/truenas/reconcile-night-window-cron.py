#!/usr/bin/env python3
"""Reconcile the TrueNAS cron jobs that run config/truenas/night-window-apps.txt at night only.

The jobs reuse restore-optional-apps.sh --start/--stop with that list. --check is
offline; --apply creates missing jobs as root on the canonical checkout and refuses drift.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

CHECKOUT = Path("/mnt/cpool/compose/nabla-compose")
APPS_FILE = CHECKOUT / "config/truenas/night-window-apps.txt"
SCRIPT = CHECKOUT / "scripts/truenas/restore-optional-apps.sh"


def job(name: str, mode: str, hour: str, dow: str) -> dict:
    return {
        "description": name,
        "user": "root",
        "enabled": True,
        "stdout": True,
        "stderr": False,
        "schedule": {"minute": "00", "hour": hour, "dom": "*", "month": "*", "dow": dow},
        "command": f"env NABLA_OPTIONAL_APPS_FILE={APPS_FILE} bash {SCRIPT} {mode}",
    }


# Sunday 00:00 runs the cpool scrub and the cloud syncs: no start that night.
JOBS = [
    job("nabla-night-window-start", "--start", "01", "1-6"),
    job("nabla-night-window-stop", "--stop", "07", "*"),
]


def middleware(method: str, *arguments: object) -> object:
    argv = ["midclt", "call", method, *(json.dumps(v) for v in arguments)]
    result = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=30)
    if result.returncode:
        raise RuntimeError(f"TrueNAS middleware {method} failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"TrueNAS middleware {method} returned invalid JSON") from exc


def same_contract(entry: dict, spec: dict) -> bool:
    return all(entry.get(key) == spec[key] for key in ("user", "command", "schedule"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.check:
        for spec in JOBS:
            s = spec["schedule"]
            print(f"CHECK: {spec['description']} {s['minute']} {s['hour']} * * {s['dow']} :: {spec['command']}")
        return 0
    if os.geteuid() != 0 or CHECKOUT.is_symlink() or not APPS_FILE.is_file():
        raise RuntimeError("run as root on the canonical TrueNAS checkout that holds the night-window list")
    records = middleware("cronjob.query")
    if not isinstance(records, list):
        raise RuntimeError("cronjob.query returned non-array")
    for spec in JOBS:
        matches = [r for r in records if isinstance(r, dict) and r.get("description") == spec["description"]]
        if len(matches) > 1:
            raise RuntimeError(f"duplicate cron jobs {spec['description']}; reconcile manually")
        if matches and not same_contract(matches[0], spec):
            raise RuntimeError(f"cron job {spec['description']} drifted; refuse mutation")
        if matches:
            print(f"EXISTS: {spec['description']}")
            continue
        middleware("cronjob.create", spec)
        print(f"CREATED: {spec['description']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"REJECTED: {exc}") from None
