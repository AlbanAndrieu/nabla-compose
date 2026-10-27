#!/usr/bin/env python3
"""Read-only PostgreSQL session and lock-wait triage for DefectDojo.

Never returns SQL query text, credentials, psql stderr or database rows.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

CONTAINER = "ix-postgres-postgres-1"
SQL = """SELECT COALESCE(json_agg(row_to_json(s)), '[]'::json)
FROM (
  SELECT COALESCE(state, 'unknown') state,
         COALESCE(wait_event_type,'none') wait_type,
         COALESCE(wait_event,'none') wait_event,
         count(*)::integer sessions,
         round(max(extract(epoch from clock_timestamp()-query_start))::numeric)::integer oldest_query_seconds,
         count(*) FILTER(WHERE cardinality(pg_blocking_pids(pid))>0)::integer blocked_sessions
  FROM pg_stat_activity WHERE datname='defectdojo'
  GROUP BY state, wait_event_type, wait_event
  ORDER BY count(*) DESC LIMIT 24
) s"""
SAFE = re.compile(r"^[a-zA-Z0-9_ -]{1,60}$")


def execute(args: list[str]) -> str | None:
    try:
        p = subprocess.run(args, capture_output=True, timeout=12, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode or len(p.stdout) > 8192:
        return None
    return p.stdout.decode("utf-8", "replace").strip()


def inspect() -> dict[str, object]:
    report: dict[str, object] = {
        "schema": "nabla-defectdojo-postgres-waits/v1", "database": "defectdojo",
        "state": "UNVERIFIED", "sql_mutated": False, "query_text_exposed": False,
    }
    role = execute(["docker", "exec", CONTAINER, "sh", "-c",
                    'printf "%s" "${POSTGRES_USER:-postgres}"'])
    if not role or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", role):
        report["reason"] = "POSTGRES_ROLE_UNVERIFIED"
        return report
    raw = execute(["docker", "exec", CONTAINER, "psql", "--no-psqlrc",
                   "--set=ON_ERROR_STOP=1", "--tuples-only", "--no-align",
                   "-U", role, "-d", "postgres", "--command", SQL])
    try:
        groups = json.loads(raw) if raw is not None else None
    except (ValueError, TypeError):
        groups = None
    if not isinstance(groups, list):
        report["reason"] = "SESSION_QUERY_UNAVAILABLE"
        return report
    sanitized = []
    for record in groups:
        if not isinstance(record, dict):
            continue
        state = str(record.get("state", "unknown"))
        kind = str(record.get("wait_type", "none"))
        event = str(record.get("wait_event", "none"))
        count = record.get("sessions")
        blocked = record.get("blocked_sessions")
        age = record.get("oldest_query_seconds")
        if not all(SAFE.fullmatch(v) for v in (state, kind, event)):
            continue
        if (type(count) is not int or count < 0 or type(blocked) is not int
                or blocked < 0 or blocked > count):
            continue
        sanitized.append({
            "state": state, "wait_type": kind, "wait_event": event,
            "sessions": count, "blocked_sessions": blocked,
            "oldest_query_seconds": max(0, min(age, 86400 * 365))
                if type(age) is int else None,
        })
    report["sessions"] = sanitized
    report["state"] = (
        "LOCK_WAIT_OBSERVED"
        if any(s["blocked_sessions"] or s["wait_type"] == "Lock"
               for s in sanitized) else "NO_LOCK_WAIT_OBSERVED"
    )
    report["note"] = "A single SQL snapshot cannot prove initializer completion"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    report = inspect()
    print(json.dumps(report, sort_keys=True, indent=2))
    return 1 if report["state"] == "LOCK_WAIT_OBSERVED" else (
        0 if report["state"] == "NO_LOCK_WAIT_OBSERVED" else 2
    )


if __name__ == "__main__":
    sys.exit(main())
