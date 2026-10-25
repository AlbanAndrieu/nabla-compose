#!/usr/bin/env python3
"""Run a bounded allowlist of independent TrueNAS diagnostics, read-only.

This coordinator never streams child output because logs, paths and HTTP
responses can contain secrets. Run individual scripts on the trusted host to
read their own carefully redacted findings. No shell, restart, deploy or sudo.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Check:
    name: str
    args: tuple[str, ...]
    timeout: int


# Fixed sources only. No interpolation of user input into paths or URLs.
CHECKS: dict[str, tuple[Check, ...]] = {
    "observability": (
        Check(
            "prometheus_target_scrapes",
            ("python3", "scripts/prometheus/diagnose-failed-scrapes.py", "--check"),
            15,
        ),
        Check(
            "prometheus_pyroscope_readiness",
            ("bash", "scripts/truenas/diagnose-observability-post-repair.sh", "--check"),
            35,
        ),
        Check(
            "postgres_exporter",
            ("bash", "scripts/truenas/diagnose-postgres-exporter.sh"),
            15,
        ),
        Check(
            "gatus_monitors",
            ("python3", "scripts/truenas/diagnose-gatus-monitors.py", "--check"),
            20,
        ),
    ),
    "applications": (
        Check(
            "gatus",
            ("bash", "scripts/truenas/diagnose-gatus.sh"),
            35,
        ),
        Check(
            "openrag_startup",
            ("bash", "scripts/truenas/diagnose-openrag-startup.sh", "--check"),
            45,
        ),
    ),
}
SECTIONS = (*CHECKS, "all")


def selected_checks(section: str) -> tuple[Check, ...]:
    """Preserve the declared order without allowing arbitrary commands."""
    if section == "all":
        return tuple(check for group in CHECKS.values() for check in group)
    return CHECKS[section]


def collect(
    checks: tuple[Check, ...],
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> list[dict[str, object]]:
    """Run every selected check; one failure never skips a later check."""
    results: list[dict[str, object]] = []
    for check in checks:
        path = ROOT / check.args[1]
        if not path.is_file():
            status = "not_installed"
            exit_code = None
        else:
            try:
                # stdout/stderr can contain credentials from a lower-level
                # dependency. Suppress them rather than storing private logs.
                finished = runner(
                    check.args,
                    cwd=ROOT,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=check.timeout,
                )
            except subprocess.TimeoutExpired:
                status, exit_code = "timeout", None
            except OSError:
                status, exit_code = "not_executed", None
            else:
                exit_code = finished.returncode
                status = (
                    "pass" if exit_code == 0
                    else "unverified" if exit_code == 2
                    else "failed"
                )
        results.append(
            {"name": check.name, "state": status, "exit_code": exit_code}
        )
    return results


def overall_exit(results: list[dict[str, object]]) -> int:
    """Never declare PASS when any service lacks fresh evidence."""
    states = {str(item["state"]) for item in results}
    if "failed" in states or "timeout" in states:
        return 1
    if states != {"pass"}:
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--section", choices=SECTIONS, default="observability")
    args = parser.parse_args()
    if args.plan == args.check:
        parser.error("choose exactly one of --plan or --check")

    checks = selected_checks(args.section)
    if args.plan:
        print(json.dumps({
            "mode": "plan", "section": args.section,
            "checks": [check.name for check in checks],
            "mutations": False,
        }, sort_keys=True))
        return 0

    results = collect(checks)
    exit_code = overall_exit(results)
    print(json.dumps({
        "schema_version": 1,
        "mode": "read_only",
        "section": args.section,
        "checks": results,
        "state": ("pass" if exit_code == 0 else
                  "failed" if exit_code == 1 else "unverified"),
        "mutations": False,
    }, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
