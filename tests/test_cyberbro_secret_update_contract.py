from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RENDERER_PATH = ROOT / "scripts" / "secrets" / "render_from_bitwarden.py"
IMPORTER_PATH = ROOT / "scripts" / "secrets" / "import_env_to_bitwarden.py"

renderer_spec = importlib.util.spec_from_file_location(
    "render_from_bitwarden", RENDERER_PATH
)
assert renderer_spec and renderer_spec.loader
renderer = importlib.util.module_from_spec(renderer_spec)
renderer_spec.loader.exec_module(renderer)

importer_spec = importlib.util.spec_from_file_location(
    "import_env_to_bitwarden", IMPORTER_PATH
)
assert importer_spec and importer_spec.loader
with mock.patch.dict("sys.modules", {"render_from_bitwarden": renderer}):
    importer = importlib.util.module_from_spec(importer_spec)
    importer_spec.loader.exec_module(importer)


def test_partial_optional_update_preserves_omitted_existing_provider() -> None:
    app_spec = {
        "app": "cyberbro",
        "item": "nabla/prod/cyberbro",
        "secrets": [
            {
                "env": "VIRUSTOTAL",
                "importEnv": "CYBERBRO_VIRUSTOTAL",
                "field": "VIRUSTOTAL",
                "allowEmpty": True,
            },
            {
                "env": "SHODAN",
                "importEnv": "CYBERBRO_SHODAN",
                "field": "SHODAN",
                "allowEmpty": True,
            },
        ],
    }
    existing = {
        "name": "nabla/prod/cyberbro",
        "folderId": "folder-id",
        "login": {"username": "homelab:cyberbro"},
        "fields": [
            {"name": "VIRUSTOTAL", "value": "old-vt", "type": 1},
            {"name": "SHODAN", "value": "keep-shodan", "type": 1},
        ],
    }

    with mock.patch.dict(
        os.environ,
        {"CYBERBRO_VIRUSTOTAL": "new-vt"},
        clear=True,
    ):
        values = importer.collect_values(app_spec)
        item = importer.make_item(
            app_spec=app_spec,
            folder_id="folder-id",
            values=values,
            existing=existing,
        )

    fields = {field["name"]: field["value"] for field in item["fields"]}
    assert fields["VIRUSTOTAL"] == "new-vt"
    assert fields["SHODAN"] == "keep-shodan"


def test_explicit_empty_optional_update_clears_provider() -> None:
    app_spec = {
        "app": "cyberbro",
        "item": "nabla/prod/cyberbro",
        "secrets": [
            {
                "env": "VIRUSTOTAL",
                "importEnv": "CYBERBRO_VIRUSTOTAL",
                "field": "VIRUSTOTAL",
                "allowEmpty": True,
            }
        ],
    }
    existing = {
        "name": "nabla/prod/cyberbro",
        "folderId": "folder-id",
        "fields": [{"name": "VIRUSTOTAL", "value": "old-vt", "type": 1}],
    }

    with mock.patch.dict(os.environ, {"CYBERBRO_VIRUSTOTAL": ""}, clear=True):
        values = importer.collect_values(app_spec)
        item = importer.make_item(
            app_spec=app_spec,
            folder_id="folder-id",
            values=values,
            existing=existing,
        )

    assert item["fields"][0]["value"] == ""
