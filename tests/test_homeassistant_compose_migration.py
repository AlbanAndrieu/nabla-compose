"""Offline contract for the Home Assistant native App -> Custom App cutover."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "apps/homeassistant/compose.yml"
SCRIPT = ROOT / "scripts/truenas/migrate-homeassistant-to-compose.sh"


def service() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["homeassistant"]


def test_custom_app_reuses_native_data_and_lan_port() -> None:
    app = service()
    assert "/mnt/cpool/ha/config:/config" in app["volumes"]
    assert "/mnt/cpool/ha/media:/media" in app["volumes"]
    assert not any("storage0" in volume for volume in app["volumes"])
    assert app["ports"] == [{"target": 8123, "published": 30103, "host_ip": "172.17.0.24", "protocol": "tcp"}]
    tunnel = (ROOT / "terraform/cloudflare/tunnel.tofu").read_text(encoding="utf-8")
    assert '"http://172.17.0.24:30103"' in tunnel
    assert app["x-nabla"]["runtime"]["appId"] == "homeassistant"


def test_traefik_route_uses_existing_network_entrypoint_and_private_domain() -> None:
    app = service()
    labels = dict(item.split("=", 1) for item in app["labels"])
    assert labels["traefik.http.routers.homeassistant.rule"] == "Host(`homeassistant.int.albandrieu.com`)"
    assert labels["traefik.http.routers.homeassistant.entrypoints"] == "websecure"
    assert labels["traefik.http.routers.homeassistant.tls.certresolver"] == "letsencrypt"
    assert "traefik_network" in app["networks"] and "traefik" not in app["networks"]
    assert "albanandrieu" not in COMPOSE.read_text(encoding="utf-8")
    assert "privileged" not in app and "network_mode" not in app


def test_ha_dataset_is_in_the_snapshot_policy() -> None:
    policy = json.loads((ROOT / "config/truenas/snapshot-tasks.json").read_text(encoding="utf-8"))
    app_state = next(c for c in policy["classes"] if c["name"] == "app-state")
    assert "cpool/ha" in app_state["datasets"]


def test_cutover_script_is_guarded_and_reversible() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert 'NABLA_RUNTIME_CHANGE_APPROVED:-}" == "yes"' in script
    assert 'NABLA_HA_RECORDER_ACK:-}" != "new-history"' in script
    assert script.index("zfs snapshot -r") < script.index('app.stop "${NATIVE_APP_ID}"')
    assert "--rollback" in script and 'app.start "${NATIVE_APP_ID}"' in script
    assert "(app_deploy_reconcile" in script
    for forbidden in ("app.delete", "zfs destroy", "docker compose up", "docker rm", "systemctl restart"):
        assert forbidden not in script, forbidden
