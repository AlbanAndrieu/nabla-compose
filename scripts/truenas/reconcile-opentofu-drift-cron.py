#!/usr/bin/env python3
"""Reconcile a disabled TrueNAS native cron job for read-only OpenTofu drift detection.

Check mode is entirely offline. Mutation requires TrueNAS root; enabling requires
explicit approval and the protected credentials directory.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

NAME = "nabla-opentofu-drift-check"
CHECKOUT = Path("/mnt/cpool/compose/nabla-compose")
SECRETS = Path("/mnt/cpool/secrets/runtime/opentofu-drift")
MISE = Path("/root/.local/bin/mise")

JOB = {
    "description": NAME,
    "user": "root",
    "enabled": False,
    # TrueNAS semantics: hide stdout, mail stderr (drift, errors).
    "stdout": True,
    "stderr": False,
    "schedule": {
        "minute": "20",
        "hour": "05",
        "dom": "*",
        "month": "*",
        "dow": "*",
    },
    # Versions pinned like .github/workflows/terragrunt-ci.yaml.
    "command": (
        f"{MISE} exec opentofu@1.12.5 terragrunt@0.97.0 -- /usr/bin/python3 "
        f"{CHECKOUT}/scripts/infra/opentofu-drift-check.py "
        "--run --alertmanager-url http://172.17.0.24:9093"
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


def require_run_material():
    if not MISE.is_file():
        raise RuntimeError(f"missing {MISE}: install opentofu and terragrunt with mise as root")
    if not (SECRETS / "common.env").is_file():
        raise RuntimeError(f"missing {SECRETS}/common.env (read-only Garage key)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--enable", action="store_true")
    mode.add_argument("--disable", action="store_true")
    args = parser.parse_args()
    if args.check:
        print("CHECK: native TrueNAS cron, daily 05:20 appliance time; disabled by default")
        print("CHECK: plan -detailed-exitcode only, never apply; drift mailed and pushed to Alertmanager")
        return 0
    require_environment()
    old = existing_job()
    if old is not None and not same_contract(old):
        raise RuntimeError("existing owned cron configuration drift: refuse mutation")
    if args.apply:
        if old:
            print("EXISTS: native TrueNAS drift cron left unchanged")
            return 0
        # Safe preparatory registration: scheduler does NOT run yet.
        middleware("cronjob.create", JOB)
        print("CREATED: disabled native TrueNAS Cron job (no plan started)")
        return 0
    if old is None:
        raise RuntimeError("register disabled native Cron job using --apply first")
    identifier = old.get("id")
    if not isinstance(identifier, int) or identifier <= 0:
        raise RuntimeError("owned TrueNAS cron has no valid numeric ID")
    if args.enable:
        if os.environ.get("OPENTOFU_DRIFT_APPROVED") != "YES":
            raise RuntimeError("explicit OPENTOFU_DRIFT_APPROVED=YES required")
        require_run_material()
    middleware("cronjob.update", identifier, {"enabled": bool(args.enable)})
    print("UPDATED: native TrueNAS cron " + ("enabled" if args.enable else "disabled"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"REJECTED: {exc}") from None
