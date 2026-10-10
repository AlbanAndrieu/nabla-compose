#!/usr/bin/env python3
"""Read-only TrueNAS post-reboot diagnostics; works even when FastAPI is down."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

SERVICES = (("postgres", 5432), ("redis", 6379), ("prometheus", 9090))
DEFAULT_HOST = "172.17.0.24"
FASTAPI_URL = "http://172.17.0.24:8091"
PROMETHEUS_READY = "http://172.17.0.24:9090/-/ready"


def check_tcp(host: str, port: int, timeout: float) -> dict[str, object]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"state": "reachable", "port": port}
    except OSError as exc:
        return {"state": "unreachable", "port": port, "error_type": type(exc).__name__}


def check_http(url: str, timeout: float) -> dict[str, object]:
    try:
        with urlopen(url, timeout=timeout) as response:  # noqa: S310 - operator-controlled LAN targets
            status = response.status
        return {"state": "ok" if status == 200 else "http_error", "http_status": status}
    except HTTPError as exc:
        return {"state": "http_error", "http_status": exc.code}
    except (OSError, URLError, ValueError) as exc:
        return {"state": "unreachable", "error_type": type(exc).__name__}


def check_container(name: str, timeout: float) -> dict[str, object]:
    try:
        completed = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", name],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"state": "unknown", "error_type": type(exc).__name__}
    if completed.returncode != 0:
        return {"state": "not_found"}
    return {"state": "running" if completed.stdout.strip() == "true" else "stopped"}


def diagnose_fastapi(script: Path, base_url: str, timeout: float) -> dict[str, object]:
    if not script.is_file():
        return {"state": "unavailable", "reason": "diagnostic_script_missing"}
    try:
        completed = subprocess.run(
            [sys.executable, str(script), "--url", base_url, "--json", "--wait-seconds", "5"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"state": "unavailable", "reason": "diagnostic_timeout"}
    if completed.returncode not in (0, 1):
        return {"state": "unavailable", "reason": "diagnostic_failed"}
    try:
        data = json.loads(completed.stdout)
    except ValueError:
        return {"state": "unavailable", "reason": "invalid_diagnostic_json"}
    dependencies = data.get("dependencies", {})
    return {
        "state": "complete" if data.get("evidence_complete") is True else "incomplete",
        "dependencies": {
            name: {"state": row.get("operational_state"), "evidence_complete": row.get("evidence_complete")}
            for name, row in dependencies.items() if isinstance(row, dict)
        },
        "evidence_gaps": data.get("evidence_gaps", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--fastapi-url", default=FASTAPI_URL)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--fastapi-script",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "fastapi-sample" / "scripts" / "diagnose-local-runtime-dependencies.py",
    )
    args = parser.parse_args()
    if not 0.1 <= args.timeout <= 15:
        parser.error("timeout must be between 0.1 and 15 seconds")
    checks: dict[str, dict[str, object]] = {
        "docker_fastapi": check_container("fastapi-sample", args.timeout),
        **{name: check_tcp(args.host, port, args.timeout) for name, port in SERVICES},
        "prometheus_ready": check_http(PROMETHEUS_READY.replace(DEFAULT_HOST, args.host), args.timeout),
        "fastapi_http": check_http(args.fastapi_url.rstrip("/") + "/api/health-board", args.timeout),
    }
    if checks["fastapi_http"]["state"] in ("ok", "http_error"):
        checks["fastapi_diagnostics"] = diagnose_fastapi(
            args.fastapi_script, args.fastapi_url, max(12.0, args.timeout + 8.0),
        )
    else:
        checks["fastapi_diagnostics"] = {"state": "blocked", "reason": "fastapi_unreachable"}

    # Socket connectivity is transport evidence, not DB authentication or app liveness.
    critical = ("docker_fastapi", "postgres", "redis", "fastapi_http")
    critical_good = ("running", "reachable", "reachable", "ok")
    failed = [
        name for name, expected in zip(critical, critical_good)
        if checks[name]["state"] != expected
    ]
    report = {
        "schema_version": 1, "mode": "post_reboot_read_only",
        "checks": checks, "critical_failures": failed,
        "state": "fail" if failed else (
            "warning" if checks["fastapi_diagnostics"]["state"] != "complete" else "ok"
        ),
    }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for name, result in checks.items():
            print(f"{name:<23} {result['state']}")
        print(f"RESULT={report['state']} critical_failures={','.join(failed) or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
