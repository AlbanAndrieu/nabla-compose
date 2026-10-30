#!/usr/bin/env python3
"""Read-only, sanitized OpenClaw Gateway health/startup/readiness triage.

No state reads, no secrets, no model requests, no raw response bodies, no
service restart. HTTP requests are loopback-only and ignore system proxies.
"""
from __future__ import annotations

import json
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

BASE = "http://127.0.0.1:18789"
ROUTES = ("healthz", "startupz", "readyz")
MAX_JSON = 32768


class DenyRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def service_status():
    try:
        done = subprocess.run(
            ["systemctl", "--user", "is-active", "openclaw-gateway.service"],
            capture_output=True, timeout=4, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    if done.returncode == 0 and done.stdout.strip() == b"active":
        return "active"
    if done.stdout.strip() in (b"inactive", b"failed", b"activating", b"deactivating"):
        return done.stdout.strip().decode("ascii")
    return "unknown"


def probe(route):
    """Return bounded status and JSON data from an approved local route."""
    if route not in ROUTES:
        raise ValueError("unsupported_probe_route")
    opener = build_opener(ProxyHandler({}), DenyRedirect())
    request = Request(BASE + "/" + route, method="GET")
    try:
        with opener.open(request, timeout=3) as response:
            code = response.status
            raw = response.read(MAX_JSON + 1)
    except HTTPError as error:
        code = error.code
        raw = error.read(MAX_JSON + 1)
    except (URLError, OSError, TimeoutError):
        return "unreachable", {}
    if len(raw) > MAX_JSON:
        return str(code), {}
    try:
        payload = json.loads(raw)
        return str(code), payload if isinstance(payload, dict) else {}
    except (ValueError, UnicodeError):
        return str(code), {}


def class_of_refusal(ready):
    """Categorize known admission failure types without printing identifiers."""
    if not isinstance(ready, dict):
        return "unknown"
    if isinstance(ready.get("stateDatabase"), dict):
        return "state_database"
    if isinstance(ready.get("pluginReload"), dict):
        return "plugin_reload"
    failing = ready.get("failing")
    if isinstance(failing, list):
        for item in failing[:32]:
            if not isinstance(item, str):
                continue
            if item.startswith("agent-database:"):
                return "agent_database"
            if item == "state-database":
                return "state_database"
            if item == "plugin-reload":
                return "plugin_reload"
        if failing:
            return "channel_or_other"
    if isinstance(ready.get("agentDatabases"), dict):
        return "agent_database"
    return "unknown"


def status_phase(body):
    if not isinstance(body, dict):
        return "unknown"
    value = body.get("status")
    if value in ("starting", "started", "draining"):
        return value
    return "unknown"


def diagnose(status, probes):
    health, startup, ready = (probes[name][0] for name in ROUTES)
    if status != "active":
        return "service_not_active"
    if health == "unreachable":
        return "listener_unreachable"
    if health != "200":
        return "http_liveness_failed"
    if startup != "200":
        return "startup_pending_or_failed"
    if ready != "200":
        return "admission_unready"
    return "ready"


def main():
    status = service_status()
    probes = {route: probe(route) for route in ROUTES}
    print("gateway_service=" + status)
    for route in ROUTES:
        print(route + "_status=" + probes[route][0])
    print("startup_phase=" + status_phase(probes["startupz"][1]))
    failure = class_of_refusal(probes["readyz"][1]) if probes["readyz"][0] != "200" else "none"
    print("readiness_blocker=" + failure)
    verdict = diagnose(status, probes)
    print("gateway_verdict=" + verdict)
    print("response_body_or_secrets_printed=false")
    return 0 if verdict == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
