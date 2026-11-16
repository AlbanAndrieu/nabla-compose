#!/usr/bin/env python3
"""Read-only Redis / TrueNAS / FastAPI dependency evidence diagnostic.

No credentials, container environment variables, or raw healthcheck/log output
are printed. Run on TrueNAS with sudo for Docker socket access.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_FASTAPI = "http://172.17.0.24:8091/api/homelab/health"
EXPECTED_PROJECT = "ix-redis"
EXPECTED_SERVICE = "redis"
EXPECTED_PORT = 30059
DEPENDENTS = ("sentry-snuba-api", "sentry")


def _command(argv: list[str], timeout: float) -> dict[str, Any]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"state": "unavailable", "reason": type(exc).__name__}
    if proc.returncode:
        error = proc.stderr.lower()
        reason = (
            "permission_denied" if "permission denied" in error
            else "not_found" if "no such object" in error or "not found" in error
            else "command_failed"
        )
        return {"state": "unavailable", "reason": reason}
    return {"state": "ok", "output": proc.stdout}


def _json_command(argv: list[str], timeout: float) -> dict[str, Any]:
    result = _command(argv, timeout)
    if result["state"] != "ok":
        return result
    try:
        return {"state": "ok", "value": json.loads(result["output"])}
    except (ValueError, TypeError):
        return {"state": "unavailable", "reason": "invalid_json"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def docker_evidence(name: str, timeout: float) -> dict[str, Any]:
    result = _json_command(["docker", "inspect", name], timeout)
    if result["state"] != "ok":
        return result
    items = result["value"]
    if not isinstance(items, list) or len(items) != 1:
        return {"state": "unavailable", "reason": "unexpected_inspect_shape"}
    item = _dict(items[0])
    state = _dict(item.get("State"))
    health = _dict(state.get("Health"))
    labels = _dict(_dict(item.get("Config")).get("Labels"))
    ports = _dict(_dict(item.get("NetworkSettings")).get("Ports"))
    mapped_ports = [
        {"host_ip": row.get("HostIp"), "host_port": row.get("HostPort")}
        for row in (ports.get("6379/tcp") or [])
        if isinstance(row, dict)
    ]
    return {
        "state": "ok",
        "name": str(item.get("Name") or "").lstrip("/"),
        "status": state.get("Status"),
        "health": health.get("Status") or "not_configured",
        "failing_streak": health.get("FailingStreak"),
        "recent_healthchecks": [
            {"exit_code": row.get("ExitCode"), "end": row.get("End")}
            for row in (health.get("Log") or [])[-3:]
            if isinstance(row, dict)
        ],
        "compose_project": labels.get("com.docker.compose.project"),
        "compose_service": labels.get("com.docker.compose.service"),
        "published_6379": mapped_ports,
        "restart_count": item.get("RestartCount"),
    }


def truenas_evidence(timeout: float) -> dict[str, Any]:
    result = _json_command(["midclt", "call", "app.query"], timeout)
    if result["state"] != "ok":
        return result
    apps = result["value"]
    if not isinstance(apps, list):
        return {"state": "unavailable", "reason": "invalid_app_query_shape"}
    matches = [app for app in apps if isinstance(app, dict) and (app.get("name") == "redis" or app.get("id") == "redis")]
    if len(matches) != 1:
        return {"state": "unavailable", "reason": "app_not_found" if not matches else "ambiguous_app_identity"}
    app = matches[0]
    workloads = _dict(app.get("active_workloads"))
    containers = workloads.get("container_details") or []
    return {
        "state": "ok",
        "app_id": app.get("id") or app.get("name"),
        "app_state": app.get("state"),
        "containers": [
            {"service_name": row.get("service_name"), "state": row.get("state")}
            for row in containers if isinstance(row, dict)
        ],
        "published_ports": [
            {
                "container_port": row.get("container_port"),
                "host_ports": [p.get("host_port") for p in row.get("host_ports", []) if isinstance(p, dict)],
            }
            for row in workloads.get("used_ports", []) if isinstance(row, dict)
        ],
    }


def tcp_evidence(host: str, port: int, timeout: float) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"state": "reachable", "host": host, "port": port}
    except OSError as exc:
        return {"state": "unreachable", "host": host, "port": port, "reason": type(exc).__name__}


def summarize_fastapi(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("services")
    if not isinstance(rows, list):
        return {"state": "unavailable", "reason": "services_not_a_list"}
    by_id = {row["id"]: row for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)}
    redis = by_id.get("redis")
    summary = _dict(payload.get("probe_summary"))
    internal = _dict(summary.get("internal"))
    unobserved = internal.get("unobserved_slots") or []
    return {
        "state": "ok",
        "checked_at": payload.get("checked_at"),
        "service_rows_in_snapshot": len(rows),
        "redis_in_current_snapshot": redis is not None,
        "redis_absence_interpretation": None if redis else "rotating_or_filtered_snapshot_not_catalog_absence",
        "redis_unobserved_internal_slot": any(
            isinstance(slot, dict) and slot.get("id") == "redis" for slot in unobserved
        ),
        "internal_probes_enabled": payload.get("internal_probes_enabled"),
        "internal_eligible": internal.get("eligible"),
        "internal_sampled": internal.get("sampled"),
        "redis": service_evidence(redis) if redis else None,
        "dependents": {
            service_id: service_evidence(by_id.get(service_id))
            for service_id in DEPENDENTS if by_id.get(service_id)
        },
    }


def service_evidence(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    keys = (
        "id", "state", "local_state", "effective_state", "dependency_state",
        "runtime_state", "runtime_app", "runtime_missing", "direct_state",
        "internal_state", "probe_source", "probe_stale", "observation_stale",
        "degraded_by", "blocked_by", "unconfirmed_dependencies",
    )
    return {key: row.get(key) for key in keys if key in row}


def fastapi_evidence(url: str, timeout: float) -> dict[str, Any]:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "nabla-redis-diagnostic/1.0"})
    try:
        with urlopen(req, timeout=timeout) as response:  # noqa: S310 - operator-chosen LAN endpoint
            body = response.read(1_048_577)
            status = response.status
    except HTTPError as exc:
        return {"state": "unavailable", "http_status": exc.code, "reason": "api_auth_required" if exc.code in (401, 403) else "http_error"}
    except (OSError, URLError, ValueError) as exc:
        return {"state": "unavailable", "reason": type(exc).__name__}
    if len(body) > 1_048_576:
        return {"state": "unavailable", "reason": "response_too_large"}
    try:
        payload = json.loads(body)
    except ValueError:
        return {"state": "unavailable", "http_status": status, "reason": "invalid_json"}
    if not isinstance(payload, dict):
        return {"state": "unavailable", "reason": "unexpected_payload"}
    result = summarize_fastapi(payload)
    result["http_status"] = status
    return result


def diagnose(host: str, api_url: str, timeout: float) -> dict[str, Any]:
    docker = docker_evidence("redis", timeout)
    exporter = docker_evidence("redis_exporter", timeout)
    truenas = truenas_evidence(max(timeout, 8.0))
    tcp = tcp_evidence(host, EXPECTED_PORT, timeout)
    fastapi = fastapi_evidence(api_url, timeout)
    identity = (
        docker.get("state") == "ok"
        and truenas.get("state") == "ok"
        and docker.get("compose_project") == EXPECTED_PROJECT
        and docker.get("compose_service") == EXPECTED_SERVICE
        and truenas.get("app_id") == "redis"
        and any(row.get("service_name") == EXPECTED_SERVICE for row in truenas.get("containers", []))
    )
    failures: list[str] = []
    warnings: list[str] = []
    if docker["state"] == "ok":
        if docker.get("status") != "running" or docker.get("health") == "unhealthy":
            failures.append("redis_docker_not_healthy")
    else:
        warnings.append("docker_observation_unavailable")
    if truenas["state"] == "ok":
        if truenas.get("app_state") != "RUNNING":
            failures.append("redis_truenas_not_running")
    else:
        warnings.append("truenas_observation_unavailable")
    if tcp["state"] != "reachable":
        warnings.append("published_port_not_reachable")
    if docker["state"] == "ok" and truenas["state"] == "ok" and not identity:
        warnings.append("docker_truenas_identity_mismatch")
    if fastapi["state"] != "ok":
        warnings.append("fastapi_observation_unavailable")
    elif fastapi.get("redis") and fastapi["redis"].get("local_state") == "warn":
        warnings.append("fastapi_redis_local_warn_check_probe_and_runtime_binding")
    if any(p.get("host_ip") in ("0.0.0.0", "::") for p in docker.get("published_6379", [])):
        warnings.append("redis_port_bound_to_all_host_interfaces_check_firewall")
    return {
        "schema_version": 1,
        "mode": "read_only",
        "docker": docker,
        "redis_exporter": exporter,
        "truenas": truenas,
        "tcp": tcp,
        "fastapi": fastapi,
        "docker_truenas_identity_consistent": identity,
        "authenticated_redis_ping": "not_tested_use_diagnose_shared_data_services",
        "failures": failures,
        "warnings": warnings,
        "result": "fail" if failures else "warn" if warnings else "ok",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only diagnostic (default)")
    parser.add_argument("--json", action="store_true", help="Machine-readable, sanitized result")
    parser.add_argument("--host", default="172.17.0.24", help="TrueNAS LAN host")
    parser.add_argument("--fastapi-url", default=DEFAULT_FASTAPI)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    if not 0.5 <= args.timeout <= 10:
        parser.error("--timeout must be between 0.5 and 10 seconds")
    report = diagnose(args.host, args.fastapi_url, args.timeout)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("Redis · TrueNAS / Docker / FastAPI · read-only")
        print(f"docker: {report['docker'].get('status', report['docker']['state'])} / {report['docker'].get('health', 'unknown')}")
        print(f"truenas: {report['truenas'].get('app_state', report['truenas']['state'])}")
        print(f"docker_truenas_identity_consistent: {report['docker_truenas_identity_consistent']}")
        print(f"tcp {args.host}:{EXPECTED_PORT}: {report['tcp']['state']}")
        api = report["fastapi"]
        print(f"fastapi: {api['state']} · snapshot_rows={api.get('service_rows_in_snapshot', 'n/a')} · redis_present={api.get('redis_in_current_snapshot', 'unknown')}")
        if api.get("redis_absence_interpretation"):
            print(f"fastapi_missing_redis: {api['redis_absence_interpretation']}")
        if api.get("redis"):
            print(f"fastapi_redis: {json.dumps(api['redis'], sort_keys=True)}")
        if api.get("dependents"):
            print(f"fastapi_dependents: {json.dumps(api['dependents'], sort_keys=True)}")
        print(f"warnings: {', '.join(report['warnings']) or 'none'}")
        print(f"failures: {', '.join(report['failures']) or 'none'}")
        print(f"RESULT={report['result']}")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
