"""Contract of the opt-in CrowdSec Cloudflare Worker bouncer (offline)."""

from __future__ import annotations

from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "crowdsec"


def service() -> dict:
    compose = yaml.safe_load((APP / "compose.yml").read_text(encoding="utf-8"))
    return compose["services"]["cloudflare-worker-bouncer"]


def config() -> dict:
    return yaml.safe_load((APP / "cloudflare-worker-bouncer.yaml").read_text(encoding="utf-8"))


def test_service_is_opt_in_pinned_hardened_and_unpublished() -> None:
    svc = service()
    assert svc["profiles"] == ["cloudflare-bouncer"]
    assert re.fullmatch(r"crowdsecurity/cloudflare-worker-bouncer:v[\d.]+@sha256:[0-9a-f]{64}", svc["image"])
    assert svc["read_only"] is True and svc["cap_drop"] == ["all"]
    assert "ports" not in svc and "network_mode" not in svc
    assert svc["env_file"] == [{"path": "/mnt/cpool/secrets/runtime/crowdsec/.env.secrets", "required": False}]
    manifest = (ROOT / "config" / "secrets" / "manifest.json").read_text(encoding="utf-8")
    for env in ("CROWDSEC_CLOUDFLARE_BOUNCER_LAPI_KEY", "CLOUDFLARE_CROWDSEC_BOUNCER_TOKEN"):
        assert f'"env": "{env}"' in manifest


def test_secrets_stay_in_the_environment_and_capi_is_not_synced() -> None:
    cfg = config()
    assert cfg["crowdsec_config"]["lapi_key"] == "${CROWDSEC_CLOUDFLARE_BOUNCER_LAPI_KEY}"
    assert cfg["crowdsec_config"]["only_include_decisions_from"] == ["cscli", "crowdsec"]
    (account,) = cfg["cloudflare_config"]["accounts"]
    assert account["token"] == "${CLOUDFLARE_CROWDSEC_BOUNCER_TOKEN}"


def test_routes_are_existing_tunnel_hostnames() -> None:
    tunnel = (ROOT / "terraform" / "cloudflare" / "tunnel.tofu").read_text(encoding="utf-8")
    hostnames = set(re.findall(r'hostname\s*=\s*"([^"]+)"', tunnel))
    (zone,) = config()["cloudflare_config"]["accounts"][0]["zones"]
    routes = zone["routes_to_protect"]
    assert routes and all(route.endswith("/*") for route in routes)
    assert {route.removesuffix("/*") for route in routes} <= hostnames
