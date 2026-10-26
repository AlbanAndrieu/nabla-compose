#!/usr/bin/env python3
"""Inspect the dedicated DefectDojo database before considering a reset.

Read-only SQL; never drops databases, deletes rows or restarts PostgreSQL.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

CONTAINER = "ix-postgres-postgres-1"
DATABASE = "defectdojo"
BUSINESS_TABLES = ("dojo_finding", "dojo_product", "dojo_engagement", "dojo_test")


def run(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True,
                                timeout=12, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("postgres_unreachable") from exc
    if result.returncode or len(result.stdout) > 8192:
        raise RuntimeError("postgres_unreachable")
    return result.stdout.strip()


def postgres_admin() -> str:
    username = run([
        "docker", "exec", CONTAINER, "sh", "-c",
        'printf "%s" "${POSTGRES_USER:-postgres}"',
    ])
    if not re.fullmatch(r"[a-zA-Z_][A-Za-z0-9_]{0,62}", username):
        raise RuntimeError("postgres_role_unverified")
    return username


def sql(user: str, database: str, statement: str) -> str:
    return run([
        "docker", "exec", CONTAINER, "psql", "--no-psqlrc",
        "--set=ON_ERROR_STOP=1", "--tuples-only", "--no-align",
        "-U", user, "-d", database, "--command", statement,
    ])


def inspect() -> dict[str, object]:
    admin = postgres_admin()
    metadata = json.loads(sql(admin, "postgres", """
SELECT json_build_object(
  'exists', EXISTS (SELECT 1 FROM pg_database WHERE datname='defectdojo'),
  'owner', (SELECT pg_get_userbyid(datdba) FROM pg_database
            WHERE datname='defectdojo'),
  'active_sessions', (SELECT count(*) FROM pg_stat_activity
                      WHERE datname='defectdojo'),
  'database_bytes', CASE WHEN EXISTS (
    SELECT 1 FROM pg_database WHERE datname='defectdojo')
    THEN pg_database_size('defectdojo') ELSE NULL END);
"""))
    if not isinstance(metadata, dict) or not metadata.get("exists"):
        return {"database": DATABASE, "state": "DATABASE_ABSENT",
                "reset_candidate": False}
    if metadata.get("owner") != "defectdojo":
        return {"database": DATABASE, "state": "OWNER_MISMATCH",
                "reset_candidate": False}
    counts: dict[str, int | None] = {}
    for table in BUSINESS_TABLES:
        exists = sql(admin, DATABASE,
                     f"SELECT to_regclass('public.{table}') IS NOT NULL")
        if exists == "t":
            count = sql(admin, DATABASE, f'SELECT count(*) FROM public."{table}"')
            if not count.isdigit():
                raise RuntimeError("row_count_unverified")
            counts[table] = int(count)
        elif exists == "f":
            counts[table] = None
        else:
            raise RuntimeError("schema_unverified")
    sessions = int(metadata.get("active_sessions", -1))
    candidate = (sessions == 0 and all(v == 0 for v in counts.values()))
    return {
        "schema": "nabla-defectdojo-db-inventory/v1",
        "database": DATABASE,
        "owner": "defectdojo",
        "active_sessions": sessions,
        "database_bytes": int(metadata["database_bytes"]),
        "business_table_counts": counts,
        "reset_candidate": candidate,
        "state": "EMPTY_BUSINESS_TABLES" if candidate else "NOT_PROVEN_EMPTY",
        "note": "Four empty business tables do not prove all integrations are unused. Require backup and operator approval before DROP.",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true", required=True)
    p.parse_args(argv)
    try:
        result = inspect()
    except (RuntimeError, ValueError, TypeError, json.JSONDecodeError):
        result = {"database": DATABASE, "state": "UNVERIFIED",
                  "reset_candidate": False}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("reset_candidate") else 2


if __name__ == "__main__":
    sys.exit(main())
