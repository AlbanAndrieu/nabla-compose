"""Keycloak exposure and realm-as-code contracts (owner decision 2026-11-06)."""

from __future__ import annotations

from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
TUNNEL = ROOT / "terraform" / "cloudflare" / "tunnel.tofu"
REALM = ROOT / "apps" / "keycloak" / "config" / "realms" / "nabla.yaml"
SCRIPT = ROOT / "scripts" / "truenas" / "apply-keycloak-config.sh"


def _keycloak_rules() -> list[tuple[str | None, str]]:
    text = TUNNEL.read_text(encoding="utf-8")
    rules = []
    for block in re.findall(r"(?ms)^      \{\n(.*?)^      \},\n", text):
        host = re.search(r'hostname\s*=\s*"([^"]+)"', block)
        if not host or host.group(1) != "keycloak.albandrieu.com":
            continue
        path = re.search(r'path\s*=\s*"([^"]+)"', block)
        service = re.search(r'service\s*=\s*"([^"]+)"', block)
        assert service is not None
        rules.append((path.group(1) if path else None, service.group(1)))
    return rules


def test_master_realm_is_refused_before_production_paths() -> None:
    rules = _keycloak_rules()

    assert rules == [
        ("^/realms/master(/|$)", "http_status:404"),
        ("^/(realms|resources|\\\\.well-known)/", "http://172.17.0.24:30238"),
        (None, "http_status:404"),
    ]


def test_nabla_realm_is_hardened_and_secret_free() -> None:
    realm = yaml.safe_load(REALM.read_text(encoding="utf-8"))

    assert realm["realm"] == "nabla"
    assert realm["enabled"] is True
    assert realm["sslRequired"] == "external"
    assert realm["registrationAllowed"] is False
    assert realm["bruteForceProtected"] is True
    assert realm["accessTokenLifespan"] <= 300
    serialized = REALM.read_text(encoding="utf-8").lower()
    assert "secret:" not in serialized and "password:" not in serialized


def test_apply_script_is_read_only_by_default_and_keeps_secret_out_of_argv() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'MODE="${1:---check}"' in script
    assert 'NABLA_RUNTIME_CHANGE_APPROVED:-}" == "yes"' in script
    assert "--env-file" in script and "chmod 0600" in script
    assert "KEYCLOAK_PASSWORD=${" not in script.replace('printf \'KEYCLOAK_PASSWORD=%s\\n\'', "")
    assert re.search(r"keycloak-config-cli:[0-9.]+-[0-9.]+@sha256:[0-9a-f]{64}", script)
    assert "realm: master" in script  # the script refuses to manage master
