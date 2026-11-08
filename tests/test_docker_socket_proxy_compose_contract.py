"""Offline contract for the repository-managed TrueNAS Docker socket proxy."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROXY = ROOT / "apps/docker-socket-proxy/compose.yml"
CONSUMERS = {
    "apps/pihole/compose.yml": "pihole-dns-sync",
    "apps/autoxpose/compose.yml": "autoxpose",
    "apps/homarr/compose.yml": "homarr",
    "apps/watchtower/compose.yml": "watchtower",
    "apps/gatus/compose.yml": "gatus",
    "apps/grafana/compose.yml": "alloy",
}
WRITE_ENDPOINTS = ("POST", "EXEC", "BUILD", "COMMIT", "SECRETS", "VOLUMES", "SWARM", "NODES", "PLUGINS", "SYSTEM")


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_proxy_is_read_only_and_unpublished() -> None:
    document = load(PROXY)
    proxy = document["services"]["docker-socket-proxy"]
    environment = {key: str(value) for key, value in proxy["environment"].items()}
    assert environment["POST"] == "0"
    for endpoint in WRITE_ENDPOINTS[1:]:
        assert environment.get(endpoint, "0") == "0", endpoint
    assert "ports" not in proxy
    assert "privileged" not in proxy
    assert proxy["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in proxy["security_opt"]
    assert proxy["volumes"] == ["/var/run/docker.sock:/var/run/docker.sock:ro"]
    assert proxy["labels"]["com.albandrieu.nabla.entity-ref"] == "component:default/docker-socket-proxy"
    assert proxy["x-nabla"]["id"] == "docker-socket-proxy"


def test_proxy_owns_the_dedicated_alias_on_docker_proxy() -> None:
    document = load(PROXY)
    networks = document["services"]["docker-socket-proxy"]["networks"]
    assert networks["docker-proxy"]["aliases"] == ["docker-socket-proxy"]
    assert document["networks"]["docker-proxy"] == {"external": True, "name": "docker-proxy"}


def test_every_consumer_joins_docker_proxy() -> None:
    for relative, service in CONSUMERS.items():
        document = load(ROOT / relative)
        assert "docker-proxy" in document["services"][service]["networks"], relative
        assert document["networks"]["docker-proxy"] == {"external": True, "name": "docker-proxy"}, relative


def test_workstation_proxy_no_longer_claims_the_truenas_identity() -> None:
    workstation = load(ROOT / "docker-compose.yml")["services"]["docker-socket-proxy"]
    assert "x-nabla" not in workstation
    assert "com.albandrieu.nabla.entity-ref" not in (workstation.get("labels") or {})
    assert str(workstation["environment"]["POST"]) == "0"


def test_deploy_script_guards_catalog_app_replacement() -> None:
    script = (ROOT / "scripts/truenas/deploy-docker-socket-proxy.sh").read_text(encoding="utf-8")
    assert 'NABLA_DOCKER_PROXY_REPLACE_APPROVED:-}" == "yes"' in script
    assert "docker network create --internal" in script
    assert "truenas_reconcile_custom_app" in script
    assert "systemctl restart docker" not in script
    assert "docker network rm" not in script
