"""Contracts for the shared PostgreSQL TLS 1.3 enablement (operator decision 2026-11-12)."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "truenas" / "enable-postgres-tls.sh"
CLIENTS = {
    "keycloak": "keycloak",
    "plumber": "plumber-api",
    "sample": "fastapi-sample",
}


def _default(name: str) -> str:
    match = re.search(rf'^{name}="\$\{{[A-Z_]+:-([^}}]+)\}}"$', SCRIPT.read_text(encoding="utf-8"), re.M)
    assert match, name
    return match.group(1)


def test_script_checks_by_default_and_enforces_tls13() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert os.access(SCRIPT, os.X_OK)
    assert "set -euo pipefail" in script
    assert 'MODE="${1:---check}"' in script
    assert "ALTER SYSTEM SET ssl_min_protocol_version = 'TLSv1.3'" in script
    assert "-verify_return_error" in script
    assert _default("TLS_HOST") == "172.17.0.24"
    assert 'SERVER_SAN="IP:${TLS_HOST},DNS:postgres,DNS:${SERVER_DNS}"' in script


def test_hostssl_rewrite_only_touches_the_remote_rule() -> None:
    rule = re.search(r"^REMOTE_RULE='([^']+)'$", SCRIPT.read_text(encoding="utf-8"), re.M).group(1)
    hba = "local all all trust\nhost all all 127.0.0.1/32 trust\nhost replication all ::1/128 trust\nhost all all all scram-sha-256\n"
    rewritten = subprocess.run(
        ["sed", "-E", f"s/^host({rule})/hostssl\\1/"], input=hba, capture_output=True, text=True, check=True
    ).stdout

    assert rewritten.splitlines() == [
        "local all all trust",
        "host all all 127.0.0.1/32 trust",
        "host replication all ::1/128 trust",
        "hostssl all all all scram-sha-256",
    ]
    assert "hostssl_enforced || enforce_hostssl" in SCRIPT.read_text(encoding="utf-8")


def test_published_ca_is_the_file_every_client_mounts() -> None:
    client_ca = _default("CLIENT_CA")

    for app, service in CLIENTS.items():
        compose = yaml.safe_load((ROOT / "apps" / app / "compose.yml").read_text(encoding="utf-8"))
        volumes = compose["services"][service]["volumes"]
        assert f"{client_ca}:/etc/nabla/pki/postgres-ca.crt:ro" in volumes, app
