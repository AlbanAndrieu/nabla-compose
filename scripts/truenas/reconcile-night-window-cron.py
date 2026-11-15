#!/usr/bin/env python3
"""Run the TrueNAS Apps the catalog schedules at night only.

Entities of catalog/generated/entities.json labelled
albandrieu.com/operational-schedule: night name the Apps (x-nabla.runtime.appId,
else the entity name). Two TrueNAS cron jobs call --start/--stop, which hand
that list to restore-optional-apps.sh. --check is offline; --apply creates
missing jobs as root on the canonical checkout and refuses drift.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

CHECKOUT = Path("/mnt/cpool/compose/nabla-compose")
REPO = Path(__file__).resolve().parents[2]
ENTITIES = "catalog/generated/entities.json"
SCHEDULE_LABEL = "albandrieu.com/operational-schedule"


def job(name: str, mode: str, hour: str, dow: str) -> dict:
    return {
        "description": name,
        "user": "root",
        "enabled": True,
        "stdout": True,
        "stderr": False,
        "schedule": {"minute": "00", "hour": hour, "dom": "*", "month": "*", "dow": dow},
        "command": f"python3 {CHECKOUT}/scripts/truenas/reconcile-night-window-cron.py {mode}",
    }


# Sunday 00:00 runs the cpool scrub and the cloud syncs: no start that night.
JOBS = [
    job("nabla-night-window-start", "--start", "01", "1-6"),
    job("nabla-night-window-stop", "--stop", "07", "*"),
]


def night_apps(root: Path) -> list[str]:
    entities = json.loads((root / ENTITIES).read_text(encoding="utf-8"))["entities"]
    return sorted({
        ((entity.get("x-nabla") or {}).get("runtime") or {}).get("appId") or entity["metadata"]["name"]
        for entity in entities
        if (entity["metadata"].get("labels") or {}).get(SCHEDULE_LABEL) == "night"
    })


def run(mode: str) -> int:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt") as listing:
        listing.write("".join(f"{app}\n" for app in night_apps(REPO)))
        listing.flush()
        return subprocess.run(
            ["bash", str(REPO / "scripts/truenas/restore-optional-apps.sh"), mode],
            env={**os.environ, "NABLA_OPTIONAL_APPS_FILE": listing.name},
            check=False,
        ).returncode


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
    mode.add_argument("--start", action="store_true")
    mode.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    if args.start or args.stop:
        return run("--start" if args.start else "--stop")
    if args.check:
        print(f"APPS: {' '.join(night_apps(REPO))}")
        for spec in JOBS:
            s = spec["schedule"]
            print(f"CHECK: {spec['description']} {s['minute']} {s['hour']} * * {s['dow']} :: {spec['command']}")
        return 0
    if os.geteuid() != 0 or CHECKOUT.is_symlink() or not (CHECKOUT / ENTITIES).is_file():
        raise RuntimeError("run as root on the canonical TrueNAS checkout that holds the catalog")
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
