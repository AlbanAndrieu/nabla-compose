#!/usr/bin/env python3
"""Diagnose a stuck TrueNAS DefectDojo deployment without changing runtime.

Read-only: app state, fixed container state, optional redacted *classes*
of recent Docker log failures, and the local HTTP listener. No passwords,
raw logs, environment, Docker inspect payloads or DB mutations are emitted.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess

APP = "defectdojo"
CONTAINERS = (
    "defectdojo-initializer",
    "defectdojo-uwsgi",
    "defectdojo-celeryworker",
    "defectdojo-celerybeat",
    "defectdojo",
)
ALLOWED_STATES = {"RUNNING", "DEPLOYING", "STOPPED", "CRASHED", "STOPPING", "UNKNOWN"}
ALLOWED_DOCKER_STATES = {"running", "exited", "created", "restarting", "paused", "dead", "removing"}
LOG_CATEGORIES = (
    ("database_connection", re.compile(r"(connection refused|database.*unavailable|could not connect to server|psycopg.*operationalerror)", re.I)),
    ("migration_or_initializer", re.compile(r"(migration.*failed|django\.db\.utils|initializer.*failed|relation .*does not exist)", re.I)),
    ("redis_unavailable", re.compile(r"(redis.*connection|broker.*unavailable|celery.*connection refused)", re.I)),
    ("missing_secret_config", re.compile(r"(DD_SECRET_KEY|DD_DATABASE_URL|ImproperlyConfigured|missing required env)", re.I)),
    ("filesystem_permission", re.compile(r"(permission denied|read-only file system|EACCES)", re.I)),
    ("memory_kill", re.compile(r"(out of memory|memoryerror|oom[- ]kill|killed process)", re.I)),
)


def command(args: list[str], *, timeout: int = 8, limit: int = 96 * 1024) -> tuple[int, str]:
    try:
        done = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return 2, ""
    if len(done.stdout) > limit:
        return 2, ""
    return done.returncode, done.stdout.decode("utf-8", "replace").strip()


def app_state() -> str:
    result, raw = command(
        ["midclt", "call", "app.query", '[["id","=","defectdojo"]]'],
        timeout=10,
    )
    if result != 0:
        return "UNVERIFIED"
    try:
        records = json.loads(raw)
        if not isinstance(records, list) or len(records) != 1:
            return "UNVERIFIED"
        record = records[0]
        if not isinstance(record, dict):
            return "UNVERIFIED"
        value = str(record.get("state", "")).upper()
        return value if value in ALLOWED_STATES else "UNVERIFIED"
    except (ValueError, TypeError):
        return "UNVERIFIED"


def container_snapshot(name: str) -> dict[str, object]:
    if name not in CONTAINERS:
        raise ValueError("unapproved container")
    template = (
        "{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}|"
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}"
    )
    status, raw = command(
        ["docker", "inspect", "--type", "container", "--format", template, name],
        timeout=6,
        limit=1024,
    )
    if status:
        return {"state": "ABSENT_OR_UNVERIFIED"}
    fields = raw.split("|")
    if len(fields) != 4 or fields[0] not in ALLOWED_DOCKER_STATES:
        return {"state": "UNVERIFIED"}
    exit_code = int(fields[1]) if fields[1].isdigit() else None
    return {
        "state": fields[0],
        "exit_code": exit_code if exit_code is not None and exit_code <= 255 else None,
        "oom_killed": fields[2] == "true" if fields[2] in ("true", "false") else None,
        "health": fields[3] if fields[3] in ("healthy", "unhealthy", "starting", "none")
        else "unverified",
    }


def redacted_log_classes(name: str) -> list[str]:
    if name not in CONTAINERS:
        raise ValueError("unapproved container")
    code, raw = command(
        ["docker", "logs", "--since", "45m", "--tail", "100", name],
        timeout=7, limit=64 * 1024,
    )
    if code:
        return ["LOGS_UNVERIFIED"]
    # Scan bounded raw text in memory only; never print or persist it.
    return [category for category, pattern in LOG_CATEGORIES if pattern.search(raw)]


def local_http() -> str:
    status, text = command([
        "curl", "--noproxy", "*", "--silent", "--show-error",
        "--output", "/dev/null", "--max-redirs", "0",
        "--connect-timeout", "2", "--max-time", "5",
        "--write-out", "%{http_code}", "http://172.17.0.24:31085/login",
    ], timeout=7, limit=32)
    if status != 0:
        return "UNREACHABLE"
    if re.fullmatch(r"[1-5]\d\d", text):
        return text
    return "UNVERIFIED"


def next_action(containers: dict[str, dict[str, object]], http: str) -> str:
    init = containers["defectdojo-initializer"]
    django = containers["defectdojo-uwsgi"]
    front = containers["defectdojo"]
    if init.get("oom_killed") or django.get("oom_killed") or front.get("oom_killed"):
        return "inspect_host_memory_pressure_and_oom_before_any_restart"
    if init.get("state") == "running":
        return "initializer_still_running_inspect_bounded_initializer_logs"
    if init.get("state") == "exited" and init.get("exit_code") not in (0, None):
        return "initializer_failed_investigate_db_migration_or_permissions"
    if init.get("state") == "exited" and init.get("exit_code") == 0 and django.get("state") != "running":
        return "initializer_completed_check_uwsgi_dependency"
    if django.get("state") == "running" and front.get("state") != "running":
        return "uwsgi_running_check_frontend_container_start"
    if django.get("state") == "running" and front.get("state") == "running" and http == "UNREACHABLE":
        return "check_host_port_binding_and_docker_network"
    return "inspect_init_backend_and_host_pressure_no_db_reset"


def diagnose(include_logs: bool) -> dict[str, object]:
    containers = {name: container_snapshot(name) for name in CONTAINERS}
    result: dict[str, object] = {
        "schema": "nabla-defectdojo-deploying/v1",
        "app_state": app_state(),
        "containers": containers,
        "origin_http": local_http(),
        "logs": "NOT_REQUESTED",
        "restarted": False,
        "database_modified": False,
    }
    if include_logs:
        result["logs"] = {name: redacted_log_classes(name)
                          for name in ("defectdojo-initializer", "defectdojo-uwsgi", "defectdojo")}
    result["next_check"] = next_action(containers, result["origin_http"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--include-log-classes", action="store_true",
                        help="scan bounded recent logs and emit only fixed error classes")
    args = parser.parse_args()
    report = diagnose(args.include_log_classes)
    print(json.dumps(report, sort_keys=True, indent=2))
    good = (report["app_state"] == "RUNNING"
            and report["origin_http"] in ("200", "301", "302", "303", "307", "308"))
    return 0 if good else 2


if __name__ == "__main__":
    raise SystemExit(main())
