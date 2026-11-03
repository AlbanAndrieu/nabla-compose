"""Offline security contract for the repository-managed bitcoind service."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps/bitcoind"


def service() -> dict:
    document = yaml.safe_load((APP / "compose.yml").read_text(encoding="utf-8"))
    return document["services"]["bitcoind"]


def config() -> dict[str, str]:
    values = {}
    for line in (APP / "bitcoin.conf").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key] = value
    return values


def test_no_published_port_and_local_cookie_rpc_only() -> None:
    app = service()
    assert "ports" not in app
    assert "network_mode" not in app
    conf = config()
    assert conf["listen"] == "0"
    assert conf["rpcbind"] == "127.0.0.1"
    assert conf["rpcallowip"] == "127.0.0.1"
    assert not {"rpcuser", "rpcpassword", "rpcauth"} & set(conf)


def test_disposable_pruned_node_without_wallet() -> None:
    conf = config()
    assert conf["disablewallet"] == "1"
    assert int(conf["prune"]) >= 550
    policy = json.loads((ROOT / "config/truenas/snapshot-tasks.json").read_text(encoding="utf-8"))
    assert "cpool/bitcoind" in {entry["dataset"] for entry in policy["noSnapshot"]}


def test_container_is_restricted_and_bounded() -> None:
    app = service()
    assert app["user"] == "568:568"
    assert app["read_only"] is True
    assert app["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in app["security_opt"]
    assert app["init"] is True
    assert app["mem_limit"]
    assert "privileged" not in app
    image = app["image"]
    assert image.startswith("bitcoin/bitcoin:") and not image.endswith(":latest")
    assert not any("docker.sock" in volume for volume in app["volumes"])
    assert "/mnt/cpool/bitcoind/node:/data" in app["volumes"]
    assert app["labels"]["com.albandrieu.nabla.entity-ref"] == "component:default/bitcoind"


def test_deploy_script_guards_catalog_app_replacement() -> None:
    script = (ROOT / "scripts/truenas/deploy-bitcoind.sh").read_text(encoding="utf-8")
    assert 'NABLA_BITCOIND_REPLACE_APPROVED:-}" == "yes"' in script
    assert "--replace-catalog-app" in script
    assert "truenas_reconcile_custom_app" in script
    assert "zfs destroy" not in script
    assert "docker compose -f" in script and "up" not in script.split("docker compose -f", 1)[1].split("\n", 1)[0]
