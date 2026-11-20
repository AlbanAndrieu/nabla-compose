#!/usr/bin/env python3
"""Reconcile one disabled-by-default native TrueNAS CTEM Amass Cron task.

No scans on --check, --apply, --check-live, --enable or --disable.
Only the separate scheduled runner executes Amass. No external workflow server.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

NAME = "nabla-ctem-amass-passive-weekly"
ROOT = Path("/mnt/cpool/compose/nabla-compose")
STORE = Path("/mnt/cpool/ctem/amass")
RUNNER = ROOT / "scripts/security/run-ctem-amass-truenas.sh"
COMPOSE = ROOT / "config/security/ctem/amass-job.compose.yml"

JOB = {
    "description": NAME,
    "user": "root",
    "enabled": False,
    "stdout": True,
    "stderr": False,
    "schedule": {
        "minute": "35",
        "hour": "05",
        "dom": "*",
        "month": "*",
        "dow": "0",
    },
    "command": f"/usr/bin/bash {RUNNER} --run",
}


def middleware(method: str, *args: object) -> object:
    proc = subprocess.run(
        ["midclt", "call", method, *(json.dumps(arg) for arg in args)],
        capture_output=True, text=True, timeout=20, check=False,
    )
    if proc.returncode:
        raise RuntimeError("TrueNAS middleware cron operation failed")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("TrueNAS middleware returned invalid JSON") from exc


def existing_job() -> dict | None:
    rows = middleware("cronjob.query")
    if not isinstance(rows, list):
        raise RuntimeError("cronjob.query returned non-array")
    matches = [row for row in rows
               if isinstance(row, dict) and row.get("description") == NAME]
    if len(matches) > 1:
        raise RuntimeError("duplicate CTEM native Cron tasks")
    return matches[0] if matches else None


def same_contract(row: dict) -> bool:
    return all(row.get(key) == JOB[key]
               for key in ("description", "user", "command", "schedule", "stdout", "stderr"))


def require_root_checkout() -> None:
    if os.geteuid() != 0 or ROOT.is_symlink() or not ROOT.is_dir():
        raise RuntimeError("must run as root on the canonical TrueNAS checkout")
    if not RUNNER.is_file() or not COMPOSE.is_file() or RUNNER.is_symlink() or COMPOSE.is_symlink():
        raise RuntimeError("CTEM runner and Compose config must exist in the canonical checkout")


def require_execution_ready() -> None:
    require_root_checkout()
    binary = STORE / "bin/amass"
    reports = STORE / "reports"
    if (STORE.is_symlink() or binary.is_symlink() or not binary.is_file()
            or not os.access(binary, os.X_OK)
            or reports.is_symlink() or not reports.is_dir()):
        raise RuntimeError("CTEM Amass binary/reports not installed")
    meta = reports.stat()
    if meta.st_uid != 0 or meta.st_mode & 0o777 != 0o700:
        raise RuntimeError("CTEM reports must be owned by root, mode 0700")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--check-live", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--enable", action="store_true")
    mode.add_argument("--disable", action="store_true")
    opts = parser.parse_args()

    if opts.check:
        print("CHECK: native TrueNAS Cron, Sundays 05:35 appliance local time")
        print("CHECK: registered DISABLED; no Amass process or Docker invocation")
        print(f"CHECK: {JOB['command']}")
        return 0
    require_root_checkout()
    prior = existing_job()
    if prior is not None and not same_contract(prior):
        raise RuntimeError("existing CTEM Cron contract drift: refuse mutation")
    if opts.check_live:
        if prior is None:
            raise RuntimeError("CTEM Cron not registered")
        print("LIVE: CTEM Cron found, contract matched, enabled=" + str(prior.get("enabled")))
        return 0
    if opts.apply:
        if prior is None:
            middleware("cronjob.create", JOB)
            print("CREATED: disabled CTEM Amass native Cron job")
        else:
            print("EXISTS: CTEM Amass native Cron job unchanged")
        return 0
    if prior is None or type(prior.get("id")) is not int or prior["id"] <= 0:
        raise RuntimeError("register the disabled CTEM Cron job with --apply first")
    if opts.enable:
        if os.environ.get("CTEM_AMASS_CRON_APPROVED") != "YES":
            raise RuntimeError("CTEM_AMASS_CRON_APPROVED=YES required after manual smoke")
        require_execution_ready()
    middleware("cronjob.update", prior["id"], {"enabled": bool(opts.enable)})
    print("UPDATED: CTEM Amass Cron " + ("enabled" if opts.enable else "disabled"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"REJECTED: {exc}") from None
