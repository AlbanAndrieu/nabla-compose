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
    "litellm": ("http://127.0.0.1:4000/health/readiness", "litellm"),
    "openrag": ("http://127.0.0.1:31060/health/collective_health", "openrag"),
    "scrutiny": ("http://172.17.0.24:31054/api/health", "scrutiny"),
    "influxdb": ("http://127.0.0.1:31055/health", "influxdb"),
    "prometheus": ("http://127.0.0.1:9090/-/ready", "prometheus"),
    "sentry": ("http://172.17.0.24:9005/_health/", "sentry"),
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


def startup_reason(name: str) -> str:
    """Read a bounded tail only when startup fails; return static safe categories.

    Raw Docker output is deliberately never returned, printed or serialized.
    The service names are allowlisted by CONTAINERS in assess().
    """
    if name not in (item for group in CONTAINERS.values() for item in group):
        return "startup reason unverified"
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", "20", name],
            capture_output=True, text=True, check=False, timeout=8
        )
        sample = (result.stdout + result.stderr)[-32768:].lower()
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        return "startup reason unavailable"
    if name == "prometheus" and "permission denied" in sample and (
            "prometheus.yml" in sample or "--config.file" in sample):
        return "Prometheus config permission denied"
    if "permission denied" in sample or "operation not permitted" in sample:
        return "startup permissions"
    if any(token in sample for token in
           ("yaml:", "parsing error", "invalid configuration", "unknown field")):
        return "startup config invalid"
    if "no such file or directory" in sample:
        return "startup file/path missing"
    if "address already in use" in sample:
        return "startup port conflict"
    if "out of memory" in sample or "oomkilled" in sample:
        return "startup memory exhaustion"
    return "startup reason unverified"


def prometheus_config_access() -> str | None:
    """POSIX mode preflight for Compose user 568:568; ACLs need independent review."""
    config = ROOT / "apps/prometheus/prometheus.yml"
    try:
        for item in (config, *config.parents):
            metadata = item.stat()
            is_config = item == config
            if is_config and not stat.S_ISREG(metadata.st_mode):
                return "Prometheus config path is not a regular file"
            if not is_config and not stat.S_ISDIR(metadata.st_mode):
                return "Prometheus config parent not a directory"
            # Docker Compose specifies user: "568:568"; root's os.access()
            # would give a false positive for a non-root container.
            if metadata.st_uid == 568:
                required = stat.S_IRUSR if is_config else stat.S_IXUSR
            elif metadata.st_gid == 568:
                required = stat.S_IRGRP if is_config else stat.S_IXGRP
            else:
                required = stat.S_IROTH if is_config else stat.S_IXOTH
            if not (stat.S_IMODE(metadata.st_mode) & required):
                if is_config:
                    return "Prometheus config POSIX read permission missing for UID/GID 568 (verify ZFS ACL)"
                return "Prometheus config directory traversal denied for UID/GID 568 (verify ZFS ACL)"
    except OSError:
        return "Prometheus config file or directory metadata unavailable"
    return None


def prometheus_query_check(opener, timeout: int) -> dict:
    """Prove PromQL API and TSDB query work, not merely the ready HTTP handler."""
    request = urllib.request.Request(
        "http://127.0.0.1:9090/api/v1/query?query=count%28up%29",
        headers={"Accept": "application/json"}
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                return {"status": "fail", "detail": "PromQL API non-200"}
            payload = response.read(65537)
        if len(payload) > 65536:
            return {"status": "unknown", "detail": "PromQL response exceeds limit"}
        data = json.loads(payload)
        result = data.get("data") if isinstance(data, dict) else None
        if not isinstance(data, dict) or data.get("status") != "success" or (
                not isinstance(result, dict)):
            return {"status": "fail", "detail": "PromQL execution failed"}
        if result.get("resultType") != "vector" or not isinstance(result.get("result"), list):
            return {"status": "fail", "detail": "PromQL response contract invalid"}
        if not result["result"]:
            return {"status": "warning", "detail": "PromQL works but no up series"}
        first = result["result"][0]
        sample = first.get("value") if isinstance(first, dict) else None
        try:
            count = float(sample[1]) if isinstance(sample, list) and (
                len(sample) == 2) else -1
        except (TypeError, ValueError):
            count = -1
        if not 0 < count < float("inf"):
            return {"status": "warning", "detail": "PromQL up series count unavailable"}
        return {"status": "ok", "detail": "Prometheus ready; PromQL count(up) succeeded"}
    except (OSError, TypeError, ValueError, urllib.error.HTTPError,
            urllib.error.URLError, TimeoutError):
        return {"status": "fail", "detail": "PromQL API unavailable"}


def docker_state(name: str) -> dict:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", name):
        raise ValueError("invalid container name")
    raw = run(["docker", "inspect", "--format",
               "{{json .State}}|{{.RestartCount}}", name])
    if raw is None:
        return {"status": "unknown", "health": "unknown"}
    try:
        state_raw, separator, restart_raw = raw.strip().rpartition("|")
        obj = json.loads(state_raw if separator else raw)
        restarts = int(restart_raw) if separator and restart_raw.isdecimal() else None
        if not isinstance(obj, dict):
            raise ValueError("invalid Docker state")
        health = obj.get("Health") or {}
        safe_reason = health_reason(health.get("Log") or []) if (
            health.get("Status") == "unhealthy") else None
        return {"status": str(obj.get("Status", "unknown")),
                "health": str(health.get("Status", "none")),
                "healthReason": safe_reason,
                "exit": obj.get("ExitCode"),
                "restarts": restarts,
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
            # Gatus includes result history for every monitor (85 in the
            # 23 October operator snapshot), so the default 64 KiB JSON bound
            # is too small. Keep a strict 4 MiB limit rather than read all.
            limit = 4 * 1024 * 1024 if kind == "gatus" else 65536
            body = resp.read(limit + 1)
        if len(body) > limit:
            if kind == "gatus":
                return {"status": "warning",
                        "detail": "Gatus API payload exceeds 4 MiB; monitors unverified"}
            return {"status": "unknown", "detail": "response exceeds limit"}
        if kind == "prometheus":
            return prometheus_query_check(opener, timeout)
        if kind == "sentry":
            return {"status": "ok", "detail": "Sentry edge HTTP 200; consumer health checked separately"}
        if kind == "openrag":
            return {"status": "ok", "detail": "OpenRAG frontend HTTP responds; Docker backend/frontend health also required"}
        data = json.loads(body)
        if kind == "litellm":
            if not isinstance(data, dict):
                return {"status": "unknown", "detail": "LiteLLM readiness JSON unverified"}
            if data.get("db") == "disconnected" or data.get("status") not in (
                    "healthy", "connected", "ready", "ok"):
                return {"status": "fail", "detail": "LiteLLM readiness failed"}
            return {"status": "ok", "detail": "LiteLLM ready; model inference not tested"}
        if kind == "gatus":
            # Aggregates only: never output endpoint names, URLs or result bodies.
            if not isinstance(data, list):
                return {"status": "warning", "detail": "Gatus API monitor list unverified"}
            counts = {"up": 0, "down": 0, "pending": 0, "unknown": 0}
            for monitor in data:
                if not isinstance(monitor, dict) or not isinstance(
                        monitor.get("results"), list):
                    counts["unknown"] += 1
                    continue
                results = monitor["results"]
                if not results:
                    counts["pending"] += 1
                    continue
                last = results[-1]
                if not isinstance(last, dict) or not isinstance(
                        last.get("success"), bool):
                    counts["unknown"] += 1
                elif last["success"]:
                    counts["up"] += 1
                else:
                    counts["down"] += 1
            total = len(data)
            details = (f"monitors={total} up={counts['up']} down={counts['down']} "
                       f"pending={counts['pending']} unknown={counts['unknown']}")
            # DOWN target is NOT Gatus outage; it is observability coverage WARN.
            if not total or counts["down"] or counts["pending"] or counts["unknown"]:
                return {"status": "warning", "detail": details}
            return {"status": "ok", "detail": details}
        if kind == "influxdb":
            if not isinstance(data, dict) or data.get("status") not in (
                    "pass", "ok", "ready"):
                return {"status": "fail", "detail": "InfluxDB not ready"}
            return {"status": "ok", "detail": "InfluxDB health pass; query/write not tested"}
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
            if not isinstance(data, dict) or not data:
                return {"status": "unknown", "detail": "Scrutiny health JSON unverified"}
            if data.get("success") is False or data.get("status") in (
                    "error", "fail", "unhealthy"):
                return {"status": "fail", "detail": "Scrutiny health reports failure"}
            return {"status": "ok", "detail": "Scrutiny health API responded"}
        return {"status": "unknown", "detail": "unclassified HTTP"}
    except (OSError, ValueError, urllib.error.HTTPError,
            urllib.error.URLError, TimeoutError):
        return {"status": "fail", "detail": "HTTP probe unavailable"}


def fastapi_provenance() -> str | None:
    """A running image can be healthy without any Git SHA attestation."""
    req = urllib.request.Request("http://127.0.0.1:8091/v2/version",
                                 headers={"Accept": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=5) as response:
            if response.status != 200:
                return "Git provenance endpoint unavailable"
            raw = response.read(4096)
        data = json.loads(raw)
        value = data.get("build_revision") if isinstance(data, dict) else None
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{40}", value):
            return "running Git SHA not attested (build_revision missing)"
        return None
    except (OSError, ValueError, TypeError):
        return "running Git SHA not attested (version endpoint unavailable)"


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
            detail = name + " " + status
            if status in ("restarting", "exited", "dead"):
                exit_code = item.get("exit")
                restarts = item.get("restarts")
                if isinstance(exit_code, int) and not isinstance(exit_code, bool):
                    detail += f" exit={exit_code}"
                if isinstance(restarts, int) and not isinstance(restarts, bool):
                    detail += f" restarts={restarts}"
                detail += " (" + startup_reason(name) + ")"
            notes.append(detail)
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

    if service == "prometheus" and docker["prometheus"]["status"] != "running":
        issue = prometheus_config_access()
        if issue:
            notes.append(issue)

    # Keep probes read-only, but skip avoidable connection attempts to
    # services which Docker already proves are not running.
    any_not_running = any(item["status"] in
                          ("created", "restarting", "exited", "dead")
                          for item in docker.values())
    http = (http_check(service) if service in HTTP and not any_not_running
            else None)
    if service in HTTP and any_not_running:
        notes.append("HTTP probe skipped: required container not running")
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
        notes.append("readiness passes but Docker healthcheck fails")
    if service == "openrag" and docker["openrag-backend"]["health"] == "healthy":
        notes.append("backend ready; frontend must also be running")
    if service == "sample" and http and http["status"] == "ok":
        provenance_issue = fastapi_provenance()
        if provenance_issue:
            if sev == "HEALTHY":
                sev = "WARN"
            notes.append(provenance_issue)
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
