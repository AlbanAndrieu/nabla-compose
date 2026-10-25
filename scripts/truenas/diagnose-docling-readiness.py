#!/usr/bin/env python3
"""Read-only Docling TrueNAS readiness classification; no PDF content or secrets."""
from __future__ import annotations

import argparse
import json
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener


def command(*args: str, timeout: int = 12) -> tuple[bool, str]:
    try:
        result = subprocess.run(args, capture_output=True, text=True,
                                check=False, timeout=timeout)
        return result.returncode == 0, result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False, ""


def app_state(payload: object) -> str:
    if not isinstance(payload, list):
        return "UNKNOWN"
    selected = [row for row in payload
                if isinstance(row, dict) and row.get("id") == "docling"]
    if len(selected) == 0:
        return "ABSENT"
    if len(selected) != 1:
        return "UNKNOWN"
    return str(selected[0].get("state", "UNKNOWN"))


def host_ready() -> str:
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open("http://172.17.0.24:5001/ready", timeout=6) as response:
            return "READY" if response.status == 200 else "HTTP_NON_200"
    except HTTPError as exc:
        return "HTTP_" + str(exc.code)
    except (URLError, TimeoutError, OSError):
        return "UNREACHABLE"


def diagnose() -> dict[str, str]:
    result: dict[str, str] = {}
    ok, payload = command("midclt", "call", "app.query",
                          '[["id","=","docling"]]', timeout=20)
    if ok:
        try:
            result["app"] = app_state(json.loads(payload))
        except ValueError:
            result["app"] = "UNKNOWN"
    else:
        result["app"] = "UNVERIFIED"
    exists, status = command("docker", "inspect", "--type", "container",
                             "--format", "{{.State.Status}}", "docling")
    result["container"] = status.strip() if exists else "ABSENT_OR_UNVERIFIED"
    # Only metadata; never fetch the container logs or environment variables.
    has_health, health = command(
        "docker", "inspect", "--type", "container", "--format",
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}unavailable{{end}}",
        "docling",
    )
    result["containerHealth"] = health.strip() if has_health else "UNVERIFIED"
    has_restarts, count = command(
        "docker", "inspect", "--type", "container", "--format",
        "{{.RestartCount}}", "docling",
    )
    result["restartCount"] = count.strip() if has_restarts and count.strip().isdigit() else "UNVERIFIED"
    result["hostReady"] = host_ready()
    valid, _ = command("docker", "exec", "openrag-backend", "curl", "-fsS",
                       "--max-time", "6", "http://docling:5001/ready")
    result["fromOpenrag"] = "READY" if valid else "UNVERIFIED"
    if (result["app"] == "RUNNING" and result["container"] == "running"
            and result["hostReady"] == "READY" and result["fromOpenrag"] == "READY"):
        result["status"] = "READY_ONLY"
        result["next"] = "run_synthetic_pdf_conversion_before_ingestion"
    elif result["app"] == "DEPLOYING" and result["container"] == "running":
        result["status"] = "INITIALIZING"
        result["next"] = "observe_docling_container_health_without_redeploy"
    elif result["app"] in ("ABSENT", "STOPPED", "CRASHED", "FAILED"):
        result["status"] = "NOT_READY"
        result["next"] = "review_docling_custom_app_and_compose_before_targeted_deploy"
    else:
        result["status"] = "UNVERIFIED"
        result["next"] = "review_docling_logs_private_and_container_ports"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args(argv)
    result = diagnose()
    print(json.dumps(result, indent=2, sort_keys=True))
    print("NOT_TESTED: PDF_conversion_ingestion_or_retrieval")
    return 0 if result["status"] == "READY_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
