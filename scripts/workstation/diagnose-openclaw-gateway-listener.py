#!/usr/bin/env python3
"""Observe OpenClaw's user service, TCP listener and Control UI (read-only).

No supervisor actions, config/state reads, stderr, URL redirects, remote
connections, model calls or raw response/process/log content are printed.
"""
from __future__ import annotations

import ipaddress
from pathlib import Path
import re
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener

UNIT = "openclaw-gateway.service"
PORT = 18789
BASE = "http://127.0.0.1:18789"
PROBES = ("healthz", "startupz", "readyz", "", "chat/main")
STATE_VALUES = ("active", "inactive", "failed", "activating", "deactivating")
RESULT_VALUES = ("success", "exit-code", "signal", "timeout", "core-dump",
                 "oom-kill", "start-limit-hit", "watchdog", "resources")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def systemd_snapshot():
    try:
        done = subprocess.run(
            ["systemctl", "--user", "show", UNIT, "--no-pager",
             "-p", "ActiveState", "-p", "SubState", "-p", "MainPID",
             "-p", "Result", "-p", "ExecMainStatus", "-p", "NRestarts"],
            capture_output=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if done.returncode != 0 or len(done.stdout) > 8192:
        return {}
    data = {}
    for line in done.stdout.decode("utf-8", "replace").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in ("ActiveState", "SubState", "MainPID",
                                  "Result", "ExecMainStatus", "NRestarts"):
            data[key] = value.strip()
    return data


def scope_of_kernel_addr(encoded, family):
    """Classify, never display, the bind address from /proc/net/tcp{,6}."""
    try:
        if family == 4:
            octets = bytes.fromhex(encoded)
            address = ipaddress.ip_address(octets[::-1])
        else:
            octets = bytes.fromhex(encoded)
            # /proc/net/tcp6 stores each 32-bit word in host byte order.
            if len(octets) != 16:
                return "other"
            address = ipaddress.ip_address(b"".join(
                octets[i:i + 4][::-1] for i in range(0, 16, 4)))
    except (ValueError, TypeError):
        return "other"
    if address.is_unspecified:
        return "wildcard"
    if address.is_loopback:
        return "loopback"
    return "other"


def scan_tcp(text, family):
    result = set()
    for line in text.splitlines()[1:]:
        columns = line.strip().split()
        if len(columns) < 4 or columns[3] != "0A":
            continue
        address, separator, hexport = columns[1].rpartition(":")
        if not separator:
            continue
        try:
            if int(hexport, 16) != PORT:
                continue
        except ValueError:
            continue
        result.add(scope_of_kernel_addr(address, family))
    return result


def listener_scope():
    scopes = set()
    count = 0
    for name, family in (("/proc/net/tcp", 4), ("/proc/net/tcp6", 6)):
        try:
            # These kernel tables do not expose process arguments/secrets.
            data = Path(name).read_text(encoding="ascii")
        except (OSError, UnicodeError):
            continue
        count += 1
        scopes.update(scan_tcp(data, family))
    if count == 0:
        return "unknown"
    if not scopes:
        return "not_listening"
    if "wildcard" in scopes:
        return "wildcard"
    if scopes == {"loopback"}:
        return "loopback"
    if scopes == {"other"}:
        return "lan_or_other"
    return "mixed_bind"


def http_status(route):
    if route not in PROBES:
        raise ValueError("unsupported_route")
    path = "/" + route if route else "/"
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(BASE + path, method="GET")
    try:
        # We need only the status, and never read the body.
        with opener.open(request, timeout=2) as response:
            code = response.status
    except HTTPError as exc:
        code = exc.code
        exc.close()
    except (URLError, OSError, TimeoutError):
        return "unreachable"
    return str(code) if isinstance(code, int) and 100 <= code <= 599 else "unknown"


def safe_state(snapshot):
    if not snapshot:
        return "unknown"
    state = snapshot.get("ActiveState")
    return state if state in STATE_VALUES else "unknown"


def safe_numeric(snapshot, name):
    value = snapshot.get(name, "") if snapshot else ""
    if re.fullmatch(r"\d{1,5}", value) and int(value) <= 9999:
        return str(int(value))
    return "unknown"


def safe_pid(snapshot):
    raw = snapshot.get("MainPID", "") if snapshot else ""
    if not re.fullmatch(r"\d{1,10}", raw):
        return "absent"
    return "present" if 0 < int(raw) <= 4294967295 else "absent"


def classify(state, scope, answers):
    if state == "failed":
        return "service_failed"
    if state != "active":
        return "service_not_active"
    if scope == "not_listening":
        return "active_without_expected_tcp_listener"
    if scope == "lan_or_other":
        return "binding_not_on_loopback"
    if answers["healthz"] == "unreachable":
        return "listener_without_loopback_http"
    if answers["healthz"] != "200":
        return "http_server_not_healthy"
    if answers[""] == "unreachable":
        return "ui_root_unreachable"
    if answers[""] in ("401", "403"):
        return "ui_auth_required"
    if answers[""] == "404" or answers[""].startswith("5"):
        return "ui_root_not_served"
    if answers["chat/main"] == "404":
        return "possibly_stale_chat_deeplink"
    if answers["startupz"] != "200":
        return "startup_pending"
    if answers["readyz"] != "200":
        return "admission_unready"
    return "gateway_http_available"


def main():
    snapshot = systemd_snapshot()
    state = safe_state(snapshot)
    scope = listener_scope()
    answers = {route: http_status(route) for route in PROBES}
    print("gateway_service=" + state)
    result = snapshot.get("Result") if snapshot else None
    print("service_result=" + (result if result in RESULT_VALUES else "unknown"))
    print("service_exit_status=" + safe_numeric(snapshot, "ExecMainStatus"))
    print("service_pid=" + safe_pid(snapshot))
    print("service_restart_count=" + safe_numeric(snapshot, "NRestarts"))
    print("expected_port_listener=" + scope)
    for route, key in (("healthz", "healthz"), ("startupz", "startupz"),
                       ("readyz", "readyz"), ("", "ui_root"),
                       ("chat/main", "chat_main")):
        print(key + "_http=" + answers[route])
    verdict = classify(state, scope, answers)
    print("gateway_listener_diagnosis=" + verdict)
    print("state_or_raw_process_output_printed=false")
    # The UI root may require login; a 401/403 is proof of an HTTP listener
    # but not a healthy authenticated chat.
    return 0 if verdict == "gateway_http_available" else 2


if __name__ == "__main__":
    raise SystemExit(main())
