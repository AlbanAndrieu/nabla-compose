#!/usr/bin/env python3
"""Compact read-only functional readiness checks for TrueNAS homelab Apps.

Evidence layers: TrueNAS lifecycle, Docker runtime/health, HTTP application
contract. Never treats "running" or an HTTP 200 alone as full functionality.
Never prints secrets, response bodies, Docker environment, or raw logs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
GATUS_CONFIG = ROOT / "apps/gatus/config/config.yml"
DEFAULT = ("gatus", "litellm", "openrag", "scrutiny", "influxdb",
           "prometheus", "sentry", "sample")
CONTAINERS = {
    "gatus": ("gatus",),
    "litellm": ("litellm",),
    "openrag": ("openrag-backend", "openrag-frontend"),
    "scrutiny": ("scrutiny", "scrutiny-collector"),
    "influxdb": ("influxdb",),
    "prometheus": ("prometheus",),
    "sentry": ("ix-sentry-sentry-web-1", "ix-sentry-sentry-events-consumer-1",
               "ix-sentry-sentry-post-process-forwarder-errors-1",
               "ix-sentry-snuba-replacer-1"),
    "sample": ("fastapi-sample",),
}
HTTP = {
    "gatus": ("http://127.0.0.1:8085/api/v1/endpoints/statuses", "gatus"),
    "litellm": ("http://127.0.0.1:4000/health/liveliness", "litellm"),
    "scrutiny": ("http://172.17.0.24:31054/api/health", "scrutiny"),
    "influxdb": ("http://127.0.0.1:31055/health", "influxdb"),
    "prometheus": ("http://127.0.0.1:9090/-/ready", "prometheus"),
    "sentry": ("http://127.0.0.1:9005/_health/", "sentry"),
    "sample": ("http://127.0.0.1:8091/health", "sample"),
}
SEVERITY = {"HEALTHY": 0, "WARN": 1, "DEGRADED": 2, "BLOCKED": 3, "UNKNOWN": 4}
COLORS = {"HEALTHY": "\033[32m", "WARN": "\033[33m",
          "DEGRADED": "\033[33m", "BLOCKED": "\033[31m",
          "UNKNOWN": "\033[35m"}
ICONS = {"HEALTHY": "✅", "WARN": "⚠️", "DEGRADED": "🟠",
         "BLOCKED": "❌", "UNKNOWN": "❔"}


def run(command: list[str], timeout: int = 15) -> str | None:
    """Return stdout only for bounded successful, allowlisted subprocesses."""
    if command[0] not in ("midclt", "docker"):
        raise ValueError("unexpected diagnostic executable")
    try:
        proc = subprocess.run(command, capture_output=True, text=True,
                              check=False, timeout=timeout)
        return proc.stdout[:1048576] if proc.returncode == 0 else None
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        return None


def apps_state() -> dict[str, str] | None:
    raw = run(["midclt", "call", "app.query"], timeout=30)
    if raw is None or len(raw) >= 1048576:
        return None
    try:
        entries = json.loads(raw)
        if not isinstance(entries, list):
            return None
        states = {}
        for item in entries:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                return None
            if item["id"] in states:
                return None
            states[item["id"]] = str(item.get("state", "UNKNOWN"))
        return states
    except (TypeError, ValueError):
        return None


def health_reason(logs: list[dict]) -> str:
    """Return bounded static categories; never expose Docker health log Output."""
    for entry in reversed(logs[-3:]):
        message = str(entry.get("Output", "")).lower()
        if any(s in message for s in ("permission denied", "operation not permitted")):
            return "healthcheck permissions"
        if any(s in message for s in ("executable file not found", "command not found",
                                      "no such file or directory")):
            return "healthcheck binary/path missing"
        if any(s in message for s in ("connection refused", "timed out", "urlerror")):
            return "healthcheck connectivity"
        if "http error" in message or "status code" in message:
            return "healthcheck HTTP response"
    return "healthcheck nonzero/unknown"


def docker_state(name: str) -> dict:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", name):
        raise ValueError("invalid container name")
    raw = run(["docker", "inspect", "--format", "{{json .State}}", name])
    if raw is None:
        return {"status": "unknown", "health": "unknown"}
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise ValueError("invalid Docker state")
        health = obj.get("Health") or {}
        safe_reason = health_reason(health.get("Log") or []) if (
            health.get("Status") == "unhealthy") else None
        return {"status": str(obj.get("Status", "unknown")),
                "health": str(health.get("Status", "none")),
                "healthReason": safe_reason,
                "exit": obj.get("ExitCode"),
                "oom": bool(obj.get("OOMKilled", False))}
    except (TypeError, ValueError, AttributeError):
        return {"status": "unknown", "health": "unknown"}


def http_check(service: str, timeout: int = 5) -> dict:
    """Semantic, bounded HTTP read; do not print bodies, headers or URLs."""
    url, kind = HTTP[service]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            if resp.status != 200:
                return {"status": "fail", "detail": "non-200 HTTP"}
            body = resp.read(65537)
        if len(body) > 65536:
            return {"status": "unknown", "detail": "response exceeds limit"}
        if kind in ("litellm", "prometheus", "sentry"):
            return {"status": "ok", "detail": "HTTP 200; semantics limited"}
        data = json.loads(body)
        if kind == "gatus":
            if isinstance(data, list):
                count = len(data)
            elif isinstance(data, dict):
                count = len(data.get("endpoints", [])) if isinstance(
                    data.get("endpoints"), list) else len(data)
            else:
                return {"status": "unknown", "detail": "unexpected API shape"}
            return {"status": "ok" if count else "warning",
                    "detail": f"monitor entries={count}"}
        if kind == "influxdb":
            if not isinstance(data, dict) or data.get("status") not in (
                    "pass", "ok", "ready"):
                return {"status": "fail", "detail": "InfluxDB not ready"}
            return {"status": "ok", "detail": "queries and writes ready"}
        if kind == "sample":
            if not isinstance(data, dict) or data.get("status") != "healthy":
                return {"status": "fail", "detail": "API health not healthy"}
            components = data.get("components", {})
            if not isinstance(components, dict) or not components:
                return {"status": "warning", "detail": "components unverified"}
            statuses = [v.get("status") if isinstance(v, dict) else v
                        for v in components.values()]
            if any(x != "healthy" for x in statuses):
                return {"status": "fail", "detail": "component health failed"}
            return {"status": "ok", "detail": f"healthy components={len(statuses)}"}
        if kind == "scrutiny":
            return {"status": "ok" if isinstance(data, dict) else "unknown",
                    "detail": "HTTP health contract present"}
        return {"status": "unknown", "detail": "unclassified HTTP"}
    except (OSError, ValueError, urllib.error.HTTPError,
            urllib.error.URLError, TimeoutError):
        return {"status": "fail", "detail": "HTTP probe unavailable"}


def gatus_access() -> str | None:
    """Only metadata; never read the generated YAML or embedded credentials."""
    try:
        path = GATUS_CONFIG
        meta = path.lstat()
        if not stat.S_ISREG(meta.st_mode):
            return "config missing or symlink"
        if meta.st_gid != 568 or not (stat.S_IMODE(meta.st_mode) & stat.S_IRGRP):
            return "generated config group read missing"
        directory = path.parent.stat()
        if not (stat.S_IMODE(directory.st_mode) & stat.S_IXGRP):
            return "generated config directory traversal missing"
        groups_raw = run(["docker", "inspect", "--format",
                          "{{json .HostConfig.GroupAdd}}", "gatus"])
        if groups_raw is None:
            return "Gatus runtime group membership unverified"
        groups = json.loads(groups_raw)
        if not isinstance(groups, list) or "568" not in [
                str(group) for group in groups]:
            return "running Gatus lacks supplemental apps GID 568"
    except (OSError, TypeError, ValueError):
        return "generated config unavailable"
    return None


def assess(service: str, states: dict[str, str] | None) -> dict:
    if service not in DEFAULT:
        raise ValueError("unsupported service")
    app = states.get(service, "MISSING") if states is not None else "UNKNOWN"
    notes: list[str] = []
    sev = "HEALTHY"
    if app in ("STOPPED", "CRASHED", "ERROR", "MISSING"):
        sev = "BLOCKED"
        notes.append("TrueNAS " + app)
    elif app == "DEPLOYING":
        sev = "DEGRADED"
        notes.append("TrueNAS still DEPLOYING")
    elif app != "RUNNING":
        sev = "UNKNOWN"
        notes.append("TrueNAS state unverified")

    docker = {name: docker_state(name) for name in CONTAINERS[service]}
    for name, item in docker.items():
        status, health = item["status"], item["health"]
        if status in ("created", "restarting", "exited", "dead"):
            sev = "BLOCKED"
            notes.append(name + " " + status)
        elif status == "unknown":
            if sev == "HEALTHY":
                sev = "UNKNOWN"
            notes.append(name + " state unknown")
        elif status == "running" and health == "unhealthy":
            if sev == "HEALTHY":
                sev = "DEGRADED"
            notes.append(name + " Docker unhealthy (" +
                         str(item.get("healthReason") or "reason unverified") + ")")
        elif status == "running" and health == "starting":
            if sev == "HEALTHY":
                sev = "DEGRADED"
            notes.append(name + " health starting")
        elif status == "running" and health == "none":
            notes.append(name + " no Docker healthcheck")

    http = http_check(service) if service in HTTP else None
    if http is not None:
        if http["status"] == "fail":
            sev = "BLOCKED"
        elif http["status"] == "warning" and sev == "HEALTHY":
            sev = "WARN"
        elif http["status"] == "unknown" and sev == "HEALTHY":
            sev = "UNKNOWN"
        notes.append(http["detail"])

    if service == "gatus":
        issue = gatus_access()
        if issue:
            if sev == "HEALTHY":
                sev = "DEGRADED"
            notes.append(issue)
    if service == "litellm" and http and http["status"] == "ok" and (
        docker["litellm"]["health"] == "unhealthy"
    ):
        notes.append("liveliness passes but Docker healthcheck fails")
    if service == "openrag" and docker["openrag-backend"]["health"] == "healthy":
        notes.append("backend ready; frontend must also be running")
    return {"service": service, "state": app, "status": sev,
            "notes": notes, "containers": docker, "http": http}


def render(rows: list[dict], *, color: str, icons: str) -> None:
    is_tty = sys.stdout.isatty()
    ansi = (color == "always" or color == "auto" and is_tty) and not os.getenv("NO_COLOR")
    emoji = icons == "always" or (icons == "auto" and sys.stdout.encoding and
                                 "UTF" in sys.stdout.encoding.upper())
    for row in rows:
        label = row["status"]
        prefix = ICONS[label] + " " if emoji else ""
        value = f"{prefix}{label:8} {row['service']:12} TrueNAS={row['state']:10}"
        if ansi:
            value = COLORS[label] + value + "\033[0m"
        print(value)
        if label != "HEALTHY":
            for note in row["notes"][:3]:
                print("  · " + note)
    counts = {key: sum(row["status"] == key for row in rows) for key in SEVERITY}
    print("Summary: " + " ".join(f"{key}={count}" for key, count in counts.items()))
    print("Read-only evidence; no App restart or configuration changes.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true", help="structured redacted report")
    parser.add_argument("--strict", action="store_true",
                        help="nonzero when BLOCKED/DEGRADED/UNKNOWN observed")
    parser.add_argument("--service", action="append", choices=DEFAULT)
    parser.add_argument("--color", default="auto", choices=("auto", "always", "never"))
    parser.add_argument("--icons", default="auto", choices=("auto", "always", "never"))
    args = parser.parse_args(argv)
    states = apps_state()
    rows = [assess(name, states) for name in (args.service or DEFAULT)]
    if args.json:
        print(json.dumps({"readOnly": True, "services": rows}, indent=2))
    else:
        render(rows, color=args.color, icons=args.icons)
    return 1 if args.strict and any(row["status"] in (
        "BLOCKED", "DEGRADED", "UNKNOWN") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
