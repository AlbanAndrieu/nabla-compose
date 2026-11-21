"""Behind Cloudflare Tunnel, Traefik and CrowdSec see the public client IP, trusted from cloudflared only."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CLOUDFLARED_CIDR = "10.200.2.0/24"  # ix-cloudflared_default, the cloudflared catalog App network
PARSER = "parsers/s02-enrich/00-nabla-traefik-cloudflare-client-ip.yaml"


def _traefik() -> tuple[dict, dict]:
    compose = yaml.safe_load((ROOT / "apps/traefik/compose.yml").read_text(encoding="utf-8"))
    return compose, compose["services"]["traefik"]


def test_traefik_trusts_forwarded_headers_from_cloudflared_only() -> None:
    compose, service = _traefik()
    flags = [arg for arg in service["command"] if "forwardedHeaders" in arg]
    assert flags == [f"--entrypoints.websecure.forwardedHeaders.trustedIPs={CLOUDFLARED_CIDR}"]
    assert "cloudflared_tunnel" in service["networks"]
    assert compose["networks"]["cloudflared_tunnel"] == {"name": "ix-cloudflared_default", "external": True}
    assert "--accesslog.fields.headers.names.Cf-Connecting-Ip=keep" in service["command"]


def test_both_bouncer_instances_take_the_edge_ip_from_cloudflared_only() -> None:
    middlewares = yaml.safe_load((ROOT / "apps/traefik/dynamic/crowdsec.yml").read_text(encoding="utf-8"))
    for name in ("crowdsec", "crowdsec-appsec"):
        bouncer = middlewares["http"]["middlewares"][name]["plugin"]["bouncer"]
        assert bouncer["forwardedHeadersTrustedIPs"] == [CLOUDFLARED_CIDR], name
        assert bouncer["forwardedHeadersCustomName"] == "Cf-Connecting-Ip", name


def test_crowdsec_rewrites_source_ip_before_geoip_and_whitelists() -> None:
    parser = yaml.safe_load((ROOT / "apps/crowdsec" / PARSER).read_text(encoding="utf-8"))
    assert f'IpInRange(evt.Meta.source_ip, "{CLOUDFLARED_CIDR}")' in parser["filter"]
    assert "IsIP(" in parser["filter"]
    assert parser.get("onsuccess", "continue") == "continue"
    assert [s["meta"] for s in parser["statics"]] == ["source_ip"]
    # Same-stage parsers run in file order: 00- precedes geoip-enrich and whitelists.
    assert sorted([Path(PARSER).name, "geoip-enrich.yaml", "whitelists.yaml"])[0] == Path(PARSER).name
    crowdsec = yaml.safe_load((ROOT / "apps/crowdsec/compose.yml").read_text(encoding="utf-8"))
    mounts = crowdsec["services"]["crowdsec"]["volumes"]
    assert f"./{PARSER}:/etc/crowdsec/{PARSER}:ro" in mounts


def test_tunnel_canary_reaches_traefik_on_the_cloudflared_network() -> None:
    tunnel = (ROOT / "terraform/cloudflare/tunnel.tofu").read_text(encoding="utf-8")
    assert '"https://traefik:443" : "http://172.17.0.24:8091"' in tunnel


def test_public_rate_limits_count_per_client_not_per_cloudflared() -> None:
    sample = (ROOT / "apps/sample/compose.yml").read_text(encoding="utf-8")
    for name in ("fastapi-sample-public-rate", "fastapi-sample-hook-rate"):
        assert f"traefik.http.middlewares.{name}.ratelimit.sourcecriterion.ipstrategy.depth=1" in sample
