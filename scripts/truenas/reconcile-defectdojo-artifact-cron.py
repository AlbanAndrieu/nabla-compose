#!/usr/bin/env python3
"""Reconcile a disabled TrueNAS native cron job for outbound DefectDojo reports.

No GitHub runner. Check mode is entirely offline. Mutation requires TrueNAS root.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

NAME = "nabla-defectdojo-github-actions-artifact-pull"
CHECKOUT = Path("/mnt/cpool/compose/nabla-compose")

JOB = {
    "description": NAME,
    "user": "root",
    "enabled": False,
    "stdout": True,
    "stderr": False,
    "schedule": {
        "minute": "50",
        "hour": "06",
        "dom": "*",
        "month": "*",
        "dow": "*",
    },
    "command": (
        "/usr/bin/python3 "
        "/mnt/cpool/compose/nabla-compose/scripts/security/"
        "poll-defectdojo-gh-artifacts.py --pull"
    ),
}


def middleware(method: str, *arguments: object) -> object:
    argv = ["midclt", "call", method, *(json.dumps(v) for v in arguments)]
    result = subprocess.run(
        argv, capture_output=True, text=True, check=False, timeout=20,
    )
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
    matches = [entry for entry in records if isinstance(entry, dict)
               and entry.get("description") == NAME]
    if len(matches) > 1:
        raise RuntimeError("duplicate owned Cron jobs; reconcile manually")
    return matches[0] if matches else None


def same_contract(entry: dict) -> bool:
    return all(entry.get(key) == JOB[key] for key in ("description", "user", "command", "schedule"))


def require_environment():
    if os.geteuid() != 0 or CHECKOUT.is_symlink() or not CHECKOUT.is_dir():
        raise RuntimeError("must run as root on canonical TrueNAS checkout")


def require_app_material():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "security"))
    from github_app_auth import configuration
    configuration()



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--enable", action="store_true")
    mode.add_argument("--disable", action="store_true")
    args = parser.parse_args()
    if args.check:
        print("CHECK: native TrueNAS cron, daily 06:50 appliance time; disabled by default")
        print("CHECK: only outbound GitHub Actions fetch, no GitHub runner or Dojo API mutation")
        return 0
    require_environment()
    old = existing_job()
    if old is not None and not same_contract(old):
        raise RuntimeError("existing owned cron configuration drift: refuse mutation")
    if args.apply:
        if old:
            print("EXISTS: native TrueNAS artifact polling cron left unchanged")
            return 0
        # Safe preparatory registration: scheduler does NOT run yet.
        middleware("cronjob.create", JOB)
        print("CREATED: disabled native TrueNAS Cron job (no polling started)")
        return 0
    if old is None:
        raise RuntimeError("register disabled native Cron job using --apply first")
    identifier = old.get("id")
    if not isinstance(identifier, int) or identifier <= 0:
        raise RuntimeError("owned TrueNAS cron has no valid numeric ID")
    if args.enable:
        if os.environ.get("DEFECTDOJO_GH_POLL_APPROVED") != "YES":
            raise RuntimeError("explicit DEFECTDOJO_GH_POLL_APPROVED=YES required")
        require_app_material()
    middleware("cronjob.update", identifier, {"enabled": bool(args.enable)})
    print("UPDATED: native TrueNAS cron " + ("enabled" if args.enable else "disabled"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"REJECTED: {exc}") from None
