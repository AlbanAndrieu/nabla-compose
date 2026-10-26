#!/usr/bin/env python3
"""Read-only DefectDojo LAN HTTPS/Traefik route triage (no secrets or bodies)."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

HOST = "defectdojo.int.albandrieu.com"
EDGE = "172.17.0.24"
HTTP = f"http://{EDGE}:31085/login?next=/"
HTTPS = f"https://{HOST}/login?next=/"
EXPECTED = {
    "traefik.enable": "true",
    "traefik.docker.network": "traefik_network",
    "traefik.http.routers.defectdojo.entrypoints": "websecure",
    "traefik.http.routers.defectdojo.tls": "true",
    "traefik.http.services.defectdojo.loadbalancer.server.port": "8080",
}


def run(command: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(command, capture_output=True, text=True, timeout=14, check=False)
        return p.returncode, p.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 2, ""


def classify_http(code: int, response: str) -> str:
    if code != 0:
        return "TCP_TLS_UNREACHABLE"
    try:
        http, mime, verify = response.split("|")
    except ValueError:
        return "HTTP_METADATA_UNVERIFIED"
    if not re.fullmatch(r"[0-9]{3}", http) or not verify.isdigit():
        return "HTTP_METADATA_UNVERIFIED"
    if verify != "0":
        return "TLS_CERTIFICATE_UNTRUSTED"
    if http == "200" and mime.lower().startswith("text/html"):
        return "LOGIN_HTML_READY"
    if http in ("301", "302", "303", "307", "308"):
        return "LOGIN_REDIRECT"
    if http == "404":
        return "ROUTER_OR_PATH_NOT_FOUND"
    if http in ("502", "503", "504"):
        return "TRAEFIK_UPSTREAM_UNAVAILABLE"
    if http in ("401", "403"):
        return "LOGIN_REQUIRES_AUTH"
    return "HTTP_UNEXPECTED"


def inspect_app() -> dict[str, str]:
    result = {"traefik_container": "UNVERIFIED", "backend_network": "UNVERIFIED",
              "router_labels": "UNVERIFIED"}
    ret, status = run(["docker", "inspect", "--type", "container",
                       "--format", "{{.State.Status}}", "traefik"])
    if ret == 0 and status in ("running", "exited", "restarting", "created"):
        result["traefik_container"] = status
    ret, networks = run(["docker", "inspect", "--type", "container",
                         "--format", "{{json .NetworkSettings.Networks}}",
                         "defectdojo"])
    if ret == 0:
        try:
            mapped = json.loads(networks)
            if isinstance(mapped, dict):
                result["backend_network"] = (
                    "SHARED" if "traefik_network" in mapped else "MISSING_TRAEFIK_NETWORK"
                )
        except ValueError:
            pass
    ret, labels = run(["docker", "inspect", "--type", "container",
                       "--format", "{{json .Config.Labels}}", "defectdojo"])
    if ret == 0:
        try:
            mapped = json.loads(labels)
            if isinstance(mapped, dict):
                result["router_labels"] = (
                    "DECLARED" if all(str(mapped.get(k, "")).lower() == v
                                      for k, v in EXPECTED.items())
                    else "ROUTE_DRIFT"
                )
        except ValueError:
            pass
    return result


def diagnose() -> dict[str, object]:
    result: dict[str, object] = {"schema": "nabla-defectdojo-route/v1"}
    for name, url in (("origin", HTTP), ("https", HTTPS)):
        command = [
            "curl", "--noproxy", "*", "--silent", "--show-error",
            "--output", "/dev/null", "--connect-timeout", "3", "--max-time", "10",
            "--max-redirs", "0",
            "--write-out", "%{http_code}|%{content_type}|%{ssl_verify_result}",
        ]
        if name == "https":
            command.extend(["--resolve", f"{HOST}:443:{EDGE}"])
        command.append(url)
        code, metadata = run(command)
        result[name] = classify_http(code, metadata)
    result.update(inspect_app())
    origin = result["origin"]
    edge = result["https"]
    if origin in ("LOGIN_HTML_READY", "LOGIN_REDIRECT") and edge != "LOGIN_HTML_READY":
        result["next_layer"] = "TRAEFIK_TLS_ROUTER"
    elif edge == "LOGIN_HTML_READY":
        result["next_layer"] = "DJANGO_LOGIN_AUTHENTICATION"
    else:
        result["next_layer"] = "APPLICATION_OR_NETWORK"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args(argv)
    outcome = diagnose()
    print(json.dumps(outcome, sort_keys=True))
    return 0 if outcome["https"] == "LOGIN_HTML_READY" else 2


if __name__ == "__main__":
    sys.exit(main())
