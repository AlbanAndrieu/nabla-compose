"""Contracts for the rotated Wazuh indexer bootstrap users."""

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SECRETS = "/mnt/cpool/secrets/runtime/wazuh/.env.secrets"


def services() -> dict:
    compose = yaml.safe_load((ROOT / "apps/wazuh/compose.yml").read_text(encoding="utf-8"))
    return compose["services"]


def test_indexer_credentials_come_from_the_runtime_file_without_defaults() -> None:
    for name in ("wazuh.manager", "wazuh.dashboard"):
        service = services()[name]
        assert {"path": RUNTIME_SECRETS, "required": True} in service["env_file"]
        assert "INDEXER_PASSWORD" not in service["environment"]
        assert "DASHBOARD_PASSWORD" not in service["environment"]


def test_indexer_mounts_the_rendered_users_not_the_template() -> None:
    volumes = services()["wazuh.indexer"]["volumes"]
    target = "/usr/share/wazuh-indexer/config/opensearch-security/internal_users.yml"
    mounts = [v for v in volumes if isinstance(v, dict) and v["target"] == target]
    assert mounts == [
        {
            "type": "bind",
            "source": "/mnt/cpool/secrets/runtime/wazuh/internal_users.yml",
            "target": target,
            "read_only": True,
            "bind": {"create_host_path": False},
        }
    ]
    assert not any(isinstance(v, str) and v.endswith(f"{target}:ro") for v in volumes)


def test_manifest_renders_the_container_variable_names() -> None:
    manifest = json.loads((ROOT / "config/secrets/manifest.json").read_text(encoding="utf-8"))
    wazuh = next(item for item in manifest["items"] if item["app"] == "wazuh")
    assert {s["env"] for s in wazuh["secrets"]} == {"INDEXER_PASSWORD", "DASHBOARD_PASSWORD"}


def test_template_keeps_every_user_the_rotation_script_hashes() -> None:
    users = yaml.safe_load(
        (ROOT / "apps/wazuh/config/wazuh_indexer/internal_users.yml").read_text(encoding="utf-8")
    )
    assert {"admin", "kibanaserver", "logstash"} <= set(users)
