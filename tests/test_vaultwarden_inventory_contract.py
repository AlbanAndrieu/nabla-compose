"""Contract tests for metadata-only Vaultwarden inventory."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/secrets/inventory_vaultwarden.py"
spec = importlib.util.spec_from_file_location("vaultwarden_inventory", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_inventory_only_reports_app_and_status() -> None:
    manifest = {
        "folder": {"name": "TrueNAS", "id": "folder-id"},
        "items": [
            {"app": "crowdsec", "item": "nabla/prod/crowdsec"},
            {"app": "cyberbro", "item": "nabla/prod/cyberbro"},
        ],
    }
    folders = [{"id": "folder-id", "name": "TrueNAS"}]
    items = [
        {"name": "nabla/prod/cyberbro", "folderId": "folder-id", "password": "SENSITIVE"},
        {"name": "nabla/prod/crowdsec", "folderId": "wrong-folder", "fields": [{"value": "SECRET"}]},
    ]
    rows, missing = module.inventory(manifest, folders, items)
    assert rows == [
        {"app": "crowdsec", "status": "missing"},
        {"app": "cyberbro", "status": "present"},
    ]
    assert missing == 1
    assert "SENSITIVE" not in str(rows)
    assert "SECRET" not in str(rows)


def test_folder_mismatch_fails_closed() -> None:
    manifest = {
        "folder": {"name": "TrueNAS", "id": "folder-id"},
        "items": [{"app": "crowdsec", "item": "nabla/prod/crowdsec"}],
    }
    rows, failures = module.inventory(
        manifest, [{"id": "folder-id", "name": "Wrong"}],
        [{"name": "nabla/prod/crowdsec", "folderId": "folder-id"}],
    )
    assert rows[0]["status"] == "missing"
    assert failures > 0
