#!/usr/bin/env python3
"""Bounded native OpenClaw cron-agent session maintenance.

Uses OpenClaw Gateway-backed sessions cleanup API, never SQLite directly.
Plan is read-only. Apply is opt-in, cron-agent only, and requires successful
native dry-run first. Never prints keys, transcripts, store paths or secrets.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

# Resolves Node from the aligned mise/runtime contract; never PATH or stale release.
from runpy import run_path
NODE, CLI = run_path(str(Path(__file__).with_name("openclaw_runtime_paths.py")))["pinned_cli_paths"]()
MAX_OUTPUT = 512 * 1024
FIELDS = ("beforeCount", "afterCount", "pruned", "capped", "missing", "dmScopeRetired")
AGENT = "cron"


def owned_file(path: Path) -> bool:
    try:
        record = path.lstat()
        return (stat.S_ISREG(record.st_mode) and record.st_nlink == 1
                and record.st_uid == os.geteuid()
                and not record.st_mode & 0o022)
    except OSError:
        return False


def summarize(output: bytes, *, dry_run: bool) -> dict:
    report = {"state": "unverified", "target_agent": AGENT,
              "dry_run": dry_run, "session_identifiers_printed": False}
    if len(output) > MAX_OUTPUT or not output:
        return report
    try:
        record = json.loads(output)
    except (UnicodeError, ValueError):
        return report
    if not isinstance(record, dict) or record.get("allAgents") is True:
        return report
    stores = record.get("stores")
    if isinstance(stores, list):
        # Reject any cross-agent effects in a response, even in a plan.
        if len(stores) != 1 or not isinstance(stores[0], dict):
            return report
        entry = stores[0]
        if entry.get("agentId") != AGENT:
            return report
    elif record.get("agentId") == AGENT:
        entry = record
    else:
        return report
    fields = {}
    for key in FIELDS:
        value = entry.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            fields[key] = value
    report.update(state="structured", counters=fields)
    return report


def execute(*, apply: bool) -> tuple[dict, int]:
    base = {"operation": "apply" if apply else "dry_run",
            "scope": "cron_only", "credentials_touched": False,
            "cron_jobs_modified": False, "gateway_restart_requested": False,
            "transcripts_printed": False, "model_requests_sent": 0}
    if not owned_file(NODE) or not owned_file(CLI):
        return {**base, "state": "installation_unverified"}, 2

    def invoke(enforce: bool) -> tuple[str, dict]:
        command = [str(NODE), str(CLI), "sessions", "cleanup",
                   "--agent", AGENT, "--enforce" if enforce else "--dry-run",
                   "--json"]
        try:
            result = subprocess.run(
                command, capture_output=True, check=False, timeout=90,
                env={**os.environ, "NODE_NO_WARNINGS": "1"})
        except (OSError, subprocess.TimeoutExpired):
            return "unavailable", summarize(b"", dry_run=not enforce)
        if result.returncode or len(result.stderr) > MAX_OUTPUT:
            return "failed", summarize(b"", dry_run=not enforce)
        return "ok", summarize(result.stdout, dry_run=not enforce)

    state, preview = invoke(False)
    if state != "ok" or preview["state"] != "structured":
        return {**base, "state": "preflight_unverified"}, 2
    if not apply:
        return {**base, "state": "preview_only", "preview": preview}, 0
    state, applied = invoke(True)
    if state != "ok" or applied["state"] != "structured":
        return {**base, "state": "apply_outcome_unverified",
                "preflight": preview, "runtime_changes_possible": True}, 2
    return {**base, "state": "applied_by_native_maintenance",
            "preflight": preview, "result": applied}, 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--apply", action="store_true",
                         help="Opt-in cron-agent maintenance via native Gateway CLI")
    args = parser.parse_args(argv)
    report, result = execute(apply=args.apply)
    print(json.dumps(report, sort_keys=True))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
