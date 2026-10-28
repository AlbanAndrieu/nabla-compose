"""Offline DefectDojo HTTPS route categorizer: no LAN or Docker needed."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = (Path(__file__).resolve().parents[1] /
               "scripts/truenas/diagnose-defectdojo-https-route.py")
SPEC = importlib.util.spec_from_file_location("defectdojo_route_triage", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.parametrize(("exit_code", "response", "expected"), [
    (0, "200|text/html; charset=utf-8|0", "LOGIN_HTML_READY"),
    (0, "302|text/html|0", "LOGIN_REDIRECT"),
    (0, "404|text/html|0", "ROUTER_OR_PATH_NOT_FOUND"),
    (0, "502|text/html|0", "TRAEFIK_UPSTREAM_UNAVAILABLE"),
    (0, "200|text/html|60", "TLS_CERTIFICATE_UNTRUSTED"),
    (6, "", "DNS_RESOLUTION_FAILED"),
    (7, "", "TCP_TLS_UNREACHABLE"),
    (28, "", "TCP_TLS_TIMEOUT"),
    (35, "", "TLS_HANDSHAKE_FAILED"),
    (60, "", "TLS_CERTIFICATE_UNTRUSTED"),
    (2, "", "TRANSPORT_UNVERIFIED"),
    (0, "invalid", "HTTP_METADATA_UNVERIFIED"),
])
def test_classification(exit_code, response, expected):
    assert MODULE.classify_http(exit_code, response) == expected


def test_origin_ok_https_failed_points_to_traefik(monkeypatch):
    calls = []

    def fake_run(command):
        calls.append(command)
        if command[0] == "curl":
            return (0, "302|text/html|0") if command[-1] == MODULE.HTTP else (0, "404|text/html|0")
        if any(".State.Status" in token for token in command):
            return 0, "running"
        if any(".NetworkSettings.Networks" in token for token in command):
            return 0, '{"traefik_network":{}}'
        if any(".Config.Labels" in token for token in command):
            return 0, '{"traefik.enable":"true"}'
        return 2, ""

    monkeypatch.setattr(MODULE, "run", fake_run)
    report = MODULE.diagnose()
    assert report["next_layer"] == "TRAEFIK_RUNTIME_LABELS"
    assert report["traefik_container"] == "running"
    assert report["backend_network"] == "SHARED"
    assert report["router_labels"] == "ROUTE_DRIFT"
    https_call = next(x for x in calls if x[0] == "curl" and x[-1] == MODULE.HTTPS)
    assert "--resolve" in https_call
    assert f"{MODULE.HOST}:443:{MODULE.EDGE}" in https_call
    assert "--insecure" not in https_call
    assert "--noproxy" in https_call
    assert "--max-redirs" in https_call


def test_missing_container_is_unverified_not_hypothesized(monkeypatch):
    monkeypatch.setattr(MODULE, "run", lambda command: (2, ""))
    report = MODULE.diagnose()
    assert report["origin"] == "TRANSPORT_UNVERIFIED"
    assert report["https"] == "TRANSPORT_UNVERIFIED"
    assert report["router_labels"] == "UNVERIFIED"
    assert report["next_layer"] == "APPLICATION_OR_NETWORK"


def test_https_ready_independent_of_django_password(monkeypatch):
    monkeypatch.setattr(
        MODULE, "run",
        lambda command: (0, "200|text/html|0") if command[0] == "curl" else (2, ""),
    )
    assert MODULE.diagnose()["next_layer"] == "DJANGO_LOGIN_AUTHENTICATION"


def test_dns_probes_only_allowlisted_private_resolvers(monkeypatch):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        if cmd[0] == "dig":
            return 0, (
                ";; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 4\n"
                "defectdojo.int.albandrieu.com. 120 IN A 172.17.0.24"
            )
        return 2, ""

    monkeypatch.setattr(MODULE, "run", fake_run)
    assert MODULE.dns_private_a("172.17.0.1") == "PRIVATE_A_CONFIRMED"
    assert MODULE.dns_private_a("172.17.0.24") == "PRIVATE_A_CONFIRMED"
    assert all(c[0] == "dig" for c in calls)
    assert len(calls) == 2
    with pytest.raises(ValueError):
        MODULE.dns_private_a("1.1.1.1")


@pytest.mark.parametrize(("response", "result"), [
    (";; ->>HEADER<<- status: NXDOMAIN, id: 4", "PRIVATE_A_MISSING"),
    (";; ->>HEADER<<- status: SERVFAIL, id: 4", "DNS_RCODE_ERROR"),
    (";; ->>HEADER<<- status: NOERROR, id: 4", "PRIVATE_A_MISSING"),
    ("not a DNS reply", "DNS_UNVERIFIED"),
])
def test_dns_failure_states_do_not_claim_private_a(monkeypatch, response, result):
    monkeypatch.setattr(MODULE, "run", lambda args: (0, response))
    assert MODULE.dns_private_a("172.17.0.1") == result


@pytest.mark.parametrize(("ports", "result"), [
    ('{"443/tcp":[{"HostIp":"0.0.0.0","HostPort":"443"}]}', "PUBLISHED_443"),
    ('{"443/tcp":[{"HostIp":"0.0.0.0","HostPort":"8443"}]}', "MISSING_443_BINDING"),
    ('{"443/tcp":null}', "UNVERIFIED"),
    ('{}', "UNVERIFIED"),
    ('broken', "UNVERIFIED"),
])
def test_traefik_port_binding_is_classified_without_dumping_metadata(
    monkeypatch, ports, result
):
    monkeypatch.setattr(MODULE, "run", lambda args: (0, ports))
    assert MODULE.traefik_host_https() == result


@pytest.mark.parametrize(("https", "labels", "port", "network", "dns", "expected"), [
    ("LOGIN_HTML_READY", "DECLARED", "PUBLISHED_443", "SHARED",
     "PRIVATE_A_CONFIRMED", "DJANGO_LOGIN_AUTHENTICATION"),
    ("LOGIN_REDIRECT", "DECLARED", "PUBLISHED_443", "SHARED",
     "PRIVATE_A_CONFIRMED", "DJANGO_LOGIN_AUTHENTICATION"),
    ("ROUTER_OR_PATH_NOT_FOUND", "DECLARED", "PUBLISHED_443", "SHARED",
     "PRIVATE_A_CONFIRMED", "TRAEFIK_TLS_ROUTER"),
    ("LOGIN_HTML_READY", "DECLARED", "PUBLISHED_443", "SHARED",
     "PRIVATE_A_MISSING", "SPLIT_DNS"),
    ("LOGIN_HTML_READY", "DECLARED", "MISSING_443_BINDING", "SHARED",
     "PRIVATE_A_CONFIRMED", "TRAEFIK_443_BINDING"),
    ("LOGIN_HTML_READY", "DECLARED", "PUBLISHED_443", "NOT_SHARED",
     "PRIVATE_A_CONFIRMED", "TRAEFIK_NETWORK"),
])
def test_https_route_next_layer_is_specific(
    monkeypatch, https, labels, port, network, dns, expected
):
    def fake_classify(code, body):
        return "LOGIN_HTML_READY" if body == "HTTP" else https

    def fake_run(argv):
        if argv[0] == "curl":
            return 0, "HTTP" if argv[-1] == MODULE.HTTP else "HTTPS"
        return 2, ""

    monkeypatch.setattr(MODULE, "run", fake_run)
    monkeypatch.setattr(MODULE, "classify_http", fake_classify)
    monkeypatch.setattr(MODULE, "inspect_app", lambda: {
        "traefik_container": "running",
        "backend_network": "SHARED",
        "router_labels": labels,
        "shared_proxy_network": network,
        "traefik_host_https": port,
    })
    monkeypatch.setattr(MODULE, "dns_private_a", lambda resolver: dns)
    report = MODULE.diagnose()
    assert report["next_layer"] == expected
    assert report["traffic_path"].startswith("LAN_PRIVATE_DNS")
    assert report["dns_pfsense"] == dns
    assert report["dns_pihole"] == dns
