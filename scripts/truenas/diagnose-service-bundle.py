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
from concurrent.futures import ThreadPoolExecutor
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
    # Only checks with an audited exit-1 contract prove their probe failed.
    # This never establishes whole-application availability.
    exit_one_confirms_probe_failure: bool = False


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
            exit_one_confirms_probe_failure=True,
        ),
        Check(
            "gatus_monitors",
            ("python3", "scripts/truenas/diagnose-gatus-monitors.py", "--check"),
            20,
            exit_one_confirms_probe_failure=True,
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
MAX_PARALLEL_DIAGNOSTICS = 2  # Explicit opt-in; TrueNAS may be resource constrained.


def selected_checks(section: str) -> tuple[Check, ...]:
    """Preserve the declared order without allowing arbitrary commands."""
    if section == "all":
        return tuple(check for group in CHECKS.values() for check in group)
    return CHECKS[section]


def classify_exit_code(code: object, check: Check) -> tuple[str, str]:
    """Classify *diagnostic* execution, never infer underlying service DOWN.

    Some legacy scripts exit 1 on denied or unavailable metrics; those are
    unverified unless a specific probe-failure exit contract was audited.
    """
    if type(code) is not int:
        return "unverified", "invalid_exit_code"
    if code == 0:
        return "pass", "check_completed"
    if code == 1 and check.exit_one_confirms_probe_failure:
        return "failed", "confirmed_probe_failure"
    if code == 1:
        return "unverified", "nonzero_without_structured_evidence"
    if code == 2:
        return "unverified", "diagnostic_incomplete"
    return "unverified", "unexpected_exit_code"


def check_verdict(state: str) -> str:
    """Unified verdicts: a missing script is NOT_RUN, a timeout UNVERIFIED."""
    return {
        "pass": "PASS",
        "failed": "FAIL",
        "not_installed": "NOT_RUN",
    }.get(state, "UNVERIFIED")


def run_one_check(
    check: Check, runner: Callable[..., subprocess.CompletedProcess],
) -> dict[str, object]:
    """Run one fixed, read-only diagnostic; discard all child output."""
    path = ROOT / check.args[1]
    reason = "script_missing"
    if not path.is_file():
        status, exit_code = "not_installed", None
    else:
        try:
            # Discard raw stdout/stderr: child tools may print credentials.
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
            status, reason, exit_code = "timeout", "diagnostic_timed_out", None
        except OSError:
            status, reason, exit_code = "not_executed", "execution_unavailable", None
        else:
            exit_code = finished.returncode
            status, reason = classify_exit_code(exit_code, check)
    return {
        "name": check.name,
        "state": status,
        "verdict": check_verdict(status),
        "reason": reason,
        "evidence_scope": "probe_only",
        "exit_code": exit_code,
    }


def collect(
    checks: tuple[Check, ...],
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    jobs: int = 1,
) -> list[dict[str, object]]:
    """Optionally run independent probes concurrently, preserving result order.

    Sequential by default. At most two workers to limit TrueNAS CPU/memory
    pressure; subprocess timeouts remain per check, not per entire batch.
    """
    if type(jobs) is not int or not 1 <= jobs <= MAX_PARALLEL_DIAGNOSTICS:
        raise ValueError("jobs must be 1 or 2")
    if jobs == 1 or len(checks) < 2:
        return [run_one_check(check, runner) for check in checks]
    with ThreadPoolExecutor(max_workers=jobs, thread_name_prefix="nabla-probe") as pool:
        return list(pool.map(lambda check: run_one_check(check, runner), checks))


def overall_exit(results: list[dict[str, object]]) -> int:
    """Never declare PASS when any service lacks fresh evidence."""
    states = {str(item["state"]) for item in results}
    if "failed" in states:
        return 1
    if not states or states != {"pass"}:
        return 2
    return 0


def summarize_verdicts(results: list[dict[str, object]]) -> dict[str, int]:
    """Count validated probe verdicts; do not interpret service availability."""
    verdicts = ("PASS", "FAIL", "DENIED", "UNVERIFIED", "NOT_RUN")
    summary = {verdict: 0 for verdict in verdicts}
    for item in results:
        if not isinstance(item, dict):
            summary["UNVERIFIED"] += 1
            continue
        verdict = item.get("verdict")
        # Execution state is authoritative if both fields are present.
        # Reject contradictory claims (e.g. state=failed, verdict=PASS).
        if "state" in item:
            state = item["state"]
            expected = check_verdict(state) if isinstance(state, str) else "UNVERIFIED"
            verdict = expected if expected != verdict else verdict
        if isinstance(verdict, str) and verdict in summary:
            summary[verdict] += 1
        else:
            summary["UNVERIFIED"] += 1
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--section", choices=SECTIONS, default="observability")
    parser.add_argument(
        "--jobs", type=int, choices=range(1, MAX_PARALLEL_DIAGNOSTICS + 1),
        default=1, metavar="{1,2}",
        help="independent read-only checks in parallel (default: 1, max: 2)",
    )
    args = parser.parse_args()
    if args.plan == args.check:
        parser.error("choose exactly one of --plan or --check")

    checks = selected_checks(args.section)
    if args.plan:
        print(json.dumps({
            "mode": "plan", "section": args.section,
            "checks": [check.name for check in checks],
            "jobs": args.jobs,
            "mutations": False,
        }, sort_keys=True))
        return 0

    results = collect(checks, jobs=args.jobs)
    exit_code = overall_exit(results)
    summary = summarize_verdicts(results)
    print(json.dumps({
        "schema_version": 1,
        "mode": "read_only",
        "section": args.section,
        "jobs": args.jobs,
        "checks": results,
        "summary": summary,
        "state": ("pass" if exit_code == 0 else
                  "failed" if exit_code == 1 else "unverified"),
        "verdict": {0: "PASS", 1: "FAIL", 2: "UNVERIFIED"}[exit_code],
        "availability": "UNVERIFIED",  # This report observes probes, not services.
        "mutations": False,
    }, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
