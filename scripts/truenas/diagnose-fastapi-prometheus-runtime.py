#!/usr/bin/env python3
"""Read-only TrueNAS FastAPI + Prometheus runtime preflight; never emit secrets.

Run with --check on the TrueNAS host, preferably sudo for Docker access.
Checks only container identity/status and local HTTP response status/latency.
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

SECRET_DEST = "/run/secrets/fastapi-sample-metrics.key"
PROM_URLS = {
    "readiness": "http://127.0.0.1:9090/-/ready",
    "targets": "http://127.0.0.1:9090/api/v1/targets?state=active",
}
REGEX = re.compile(r"^(running|restarting|exited|created|paused|dead)\\|(true|false)\\|([0-9]+)$")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def docker(argv: list[str]) -> str | None:
    try:
        p = subprocess.run(["docker", *argv], capture_output=True, text=True,
                           timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0 or len(p.stdout) > 1024:
        return None
    return p.stdout.strip()


def inspect() -> dict[str, object]:
    status_line = docker(["inspect", "prometheus", "--format",
                          "{{.State.Status}}|{{.State.OOMKilled}}|{{.RestartCount}}"])
    status_match = REGEX.fullmatch(status_line or "")
    if status_match:
        state, oom, restarts = status_match.groups()
        state_report: dict[str, object] = {
            "state": state, "oom_killed": oom == "true",
            "restart_count": min(int(restarts), 1000000),
        }
    else:
        state_report = {"state": "unverified"}

    mount = docker(["inspect", "prometheus", "--format",
                    '{{range .Mounts}}{{if eq .Destination "' + SECRET_DEST +
                    '"}}present{{end}}{{end}}'])
    if mount == "present":
        mounted = "yes"
    elif mount == "":
        mounted = "no"
    else:
        mounted = "unverified"

    env = docker(["exec", "fastapi-sample", "python3", "-c",
                  'import os; print("present" if os.environ.get("METRICS_SCRAPE_KEY") else "missing")'])
    if env in ("present", "missing"):
        runtime_key = env
    else:
        runtime_key = "unverified"

    readable = docker(["exec", "prometheus", "sh", "-c",
                       'test -r /run/secrets/fastapi-sample-metrics.key'])
    # A zero exit code gives stdout="" on success; on failure/absence,
    # docker() returns None without leaking stderr.
    file_readable = "yes" if readable == "" else ("no_or_unverified")

    client = build_opener(ProxyHandler({}), NoRedirect())
    http = {}
    for kind, url in PROM_URLS.items():
        started = time.monotonic()
        code = None
        state = "transport_unverified"
        try:
            with client.open(Request(url, method="GET"), timeout=3) as reply:
                code = reply.status
        except HTTPError as error:
            code = error.code
            error.close()
        except (socket.timeout, TimeoutError):
            state = "timeout"
        except URLError as error:
            reason = error.reason
            if isinstance(reason, ConnectionRefusedError):
                state = "tcp_refused"
            elif isinstance(reason, (TimeoutError, socket.timeout)):
                state = "timeout"
            else:
                state = "transport_unverified"
        except OSError:
            state = "transport_unverified"
        if code is not None:
            state = "http_" + str(code) if code in (200, 401, 403, 404, 500, 502, 503, 504) else "http_other"
        http[kind] = {"state": state, "elapsed_ms": min(round((time.monotonic()-started)*1000), 99999)}

    if state_report["state"] != "running":
        next_check = "inspect_prometheus_container_state_without_restart"
    elif http["readiness"]["state"] != "http_200":
        next_check = "inspect_local_prometheus_readiness_and_memory_pressure"
    elif http["targets"]["state"] != "http_200":
        next_check = "inspect_prometheus_target_api_timeout_without_restart"
    elif mounted != "yes" or file_readable != "yes":
        next_check = "verify_prometheus_secret_mount_readability"
    elif runtime_key != "present":
        next_check = "verify_fastapi_container_environment_presence"
    else:
        next_check = "run_allowlisted_prometheus_scrape_classification"

    return {
        "component": "fastapi_prometheus_runtime",
        "prometheus": state_report,
        "secret_mount": mounted,
        "secret_readable": file_readable,
        "fastapi_runtime_key": runtime_key,
        "local_http": http,
        "next_check": next_check,
        "scrape_accepted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args(argv)
    print(json.dumps(inspect(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
