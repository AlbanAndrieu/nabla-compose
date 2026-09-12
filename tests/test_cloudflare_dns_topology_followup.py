from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "scripts" / "generate-service-topology.py"
SPEC = importlib.util.spec_from_file_location("generate_service_topology_followup", GENERATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


def test_sample_staging_declares_cloudflare_tunnel_and_access_path() -> None:
    compose = yaml.safe_load((ROOT / "apps" / "sample" / "compose.yml").read_text(encoding="utf-8"))
    metadata = compose["services"]["fastapi-sample"]["x-nabla"]
    environments = {item["name"]: item for item in metadata["environments"]}

    assert environments["staging"] == {
        "name": "staging",
        "url": "https://sample.albandrieu.com/api",
        "external": True,
        "cloudflareTunnel": True,
    }
    cloudflare_relation = next(
        relation
        for relation in metadata["relations"]
        if relation["target"] == "cloudflared"
    )
    assert cloudflare_relation["type"] == "exposedBy"


def test_hello_has_private_pihole_and_explicit_public_cloudflare_dns_owners() -> None:
    nginx = (ROOT / "apps" / "nginx" / "compose.yml").read_text(encoding="utf-8")
    pihole = (ROOT / "apps" / "pihole" / "compose.yml").read_text(encoding="utf-8")
    traefik = (ROOT / "apps" / "traefik" / "compose.yml").read_text(encoding="utf-8")
    exceptions = (ROOT / "config" / "public-int-dns-exceptions.txt").read_text(encoding="utf-8")

    assert "Host(`hello.int.albandrieu.com`)" in nginx
    assert "DOMAIN_SUFFIX: int.albandrieu.com" in pihole
    assert "TARGET_IP: 172.17.0.24" in pihole
    exception_hosts = {
        line.strip()
        for line in exceptions.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "hello.int.albandrieu.com" in exception_hosts
    assert "s3.int.albandrieu.com,hello.int.albandrieu.com,vaultwarden.int.albandrieu.com" in traefik
    assert "PROXIED=false" in traefik


def test_generated_topology_carries_monitoring_protocol_capabilities() -> None:
    topology, services = GENERATOR.generate_catalog()
    nodes = {node["id"]: node for node in topology["nodes"]}
    declared = {service["id"]: service for service in services["services"]}

    assert nodes["pfsense"]["monitoring"] == {
        "type": "http",
        "target": "https://home.albandrieu.com:10443/api/v2/system/version",
        "conditions": ["[STATUS] == 200"],
    }
    assert nodes["pfsense-unbound"]["monitoring"]["type"] == "port"
    assert nodes["pfsense-unbound"]["monitoring"]["port"] == 53
    assert nodes["pfsense-haproxy"]["monitoring"]["port"] == 443
    assert nodes["pfsense-exporter"]["kind"] == "metrics-exporter"
    assert nodes["pfsense-exporter"]["monitoring"]["type"] == "port"
    assert declared["pfsense-exporter"]["monitoring"]["target"] == "tcp://172.17.0.24:9945"
