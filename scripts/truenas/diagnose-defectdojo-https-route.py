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
    "traefik.http.routers.defectdojo.rule": "host(`defectdojo.int.albandrieu.com`)",
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
        # curl exit 60 is a certificate trust failure even when its HTTP
        # metadata is empty. Do not conflate it with a refused TCP socket.
        return {
            6: "DNS_RESOLUTION_FAILED",
            7: "TCP_TLS_UNREACHABLE",
            28: "TCP_TLS_TIMEOUT",
            35: "TLS_HANDSHAKE_FAILED",
            60: "TLS_CERTIFICATE_UNTRUSTED",
        }.get(code, "TRANSPORT_UNVERIFIED")
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


def dns_private_a(resolver: str) -> str:
    if resolver not in ("172.17.0.1", "172.17.0.24"):
        raise ValueError("unapproved DNS resolver")
    exit_code, raw = run([
        "dig", "+time=2", "+tries=1", "+noall", "+comments",
        "+answer", "@" + resolver, HOST, "A",
    ])
    if exit_code != 0 or len(raw) > 4096:
        return "DNS_UNVERIFIED"
    status = re.search(r"\bstatus:\s*([A-Z]+)", raw)
    if status is None:
        return "DNS_UNVERIFIED"
    if status.group(1) != "NOERROR":
        return "PRIVATE_A_MISSING" if status.group(1) == "NXDOMAIN" else "DNS_RCODE_ERROR"
    for line in raw.splitlines():
        fields = line.split()
        if (len(fields) >= 5 and fields[0].lower().rstrip(".") == HOST
                and fields[3].upper() == "A" and fields[4] == EDGE):
            return "PRIVATE_A_CONFIRMED"
    return "PRIVATE_A_MISSING"


def network_member(name: str) -> bool | None:
    if name not in ("traefik", "defectdojo"):
        raise ValueError("unapproved network member")
    exit_code, raw = run([
        "docker", "inspect", "--type", "container", "--format",
        "{{json .NetworkSettings.Networks}}", name,
    ])
    if exit_code != 0 or len(raw) > 8192:
        return None
    try:
        networks = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return "traefik_network" in networks if isinstance(networks, dict) else None


def traefik_host_https() -> str:
    exit_code, raw = run([
        "docker", "inspect", "--type", "container", "--format",
        "{{json .NetworkSettings.Ports}}", "traefik",
    ])
    if exit_code != 0 or len(raw) > 8192:
        return "UNVERIFIED"
    try:
        ports = json.loads(raw)
    except (ValueError, TypeError):
        return "UNVERIFIED"
    if not isinstance(ports, dict):
        return "UNVERIFIED"
    bindings = ports.get("443/tcp")
    if not isinstance(bindings, list):
        return "UNVERIFIED"
    if any(isinstance(binding, dict) and binding.get("HostPort") == "443"
           for binding in bindings):
        return "PUBLISHED_443"
    return "MISSING_443_BINDING"


def inspect_app() -> dict[str, str]:
    result = {"traefik_container": "UNVERIFIED", "backend_network": "UNVERIFIED",
              "router_labels": "UNVERIFIED", "shared_proxy_network": "UNVERIFIED",
              "traefik_host_https": traefik_host_https()}
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
    traefik_member = network_member("traefik")
    backend_member = network_member("defectdojo")
    if traefik_member is not None and backend_member is not None:
        result["shared_proxy_network"] = (
            "SHARED" if traefik_member and backend_member else "NOT_SHARED"
        )
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
    result["dns_pfsense"] = dns_private_a("172.17.0.1")
    result["dns_pihole"] = dns_private_a("172.17.0.24")
    result["traffic_path"] = "LAN_PRIVATE_DNS_DIRECT_TO_TRUENAS_NOT_PFSENSE_HAPROXY"
    origin = result["origin"]
    edge = result["https"]
    if origin not in ("LOGIN_HTML_READY", "LOGIN_REDIRECT"):
        result["next_layer"] = "APPLICATION_OR_NETWORK"
    elif result["traefik_container"] not in ("running", "UNVERIFIED"):
        result["next_layer"] = "TRAEFIK_CONTAINER"
    elif result["shared_proxy_network"] == "NOT_SHARED" or result["backend_network"] == "MISSING_TRAEFIK_NETWORK":
        result["next_layer"] = "TRAEFIK_NETWORK"
    elif result["traefik_host_https"] == "MISSING_443_BINDING":
        result["next_layer"] = "TRAEFIK_443_BINDING"
    elif result["router_labels"] == "ROUTE_DRIFT":
        result["next_layer"] = "TRAEFIK_RUNTIME_LABELS"
    elif edge not in ("LOGIN_HTML_READY", "LOGIN_REDIRECT"):
        result["next_layer"] = "TRAEFIK_TLS_ROUTER"
    elif result["dns_pfsense"] == "PRIVATE_A_MISSING" or result["dns_pihole"] == "PRIVATE_A_MISSING":
        result["next_layer"] = "SPLIT_DNS"
    else:
        result["next_layer"] = "DJANGO_LOGIN_AUTHENTICATION"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args(argv)
    outcome = diagnose()
    print(json.dumps(outcome, sort_keys=True))
    good_https = outcome["https"] in ("LOGIN_HTML_READY", "LOGIN_REDIRECT")
    good_dns = (outcome["dns_pfsense"] == "PRIVATE_A_CONFIRMED"
                and outcome["dns_pihole"] == "PRIVATE_A_CONFIRMED")
    return 0 if good_https and good_dns else 2


if __name__ == "__main__":
    sys.exit(main())
