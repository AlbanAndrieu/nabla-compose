"""Native-only identity mapping remains deterministic and unambiguous."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_generated_crosswalk_uses_only_verified_native_identifiers() -> None:
    catalog = json.loads((ROOT / "catalog/generated/entities.json").read_text())
    mapping = json.loads((ROOT / "catalog/generated/identity-map.json").read_text())
    source = yaml.safe_load(
        (ROOT / "config/monitoring/gatus-endpoints.yml").read_text()
    )
    refs = {entity["entityRef"] for entity in catalog["entities"]}
    assert mapping["catalogRevision"] == catalog["catalogRevision"]
    assert mapping["model"] == "backstage-identity-crosswalk"
    assert mapping["unresolved"] == [], "resolve missing native identifiers without guessing"
    keys = [(item["sourceType"], item["sourceId"])
            for item in mapping["mappings"]]
    assert len(keys) == len(set(keys)), "native source must have one canonical target"
    assert all(item["entityRef"] in refs for item in mapping["mappings"])
    gatus_ids = {
        endpoint["extra-labels"]["nabla_monitor_id"]
        for endpoint in source["endpoints"]
    }
    mapped_ids = {
        item["sourceId"] for item in mapping["mappings"]
        if item["sourceType"] == "gatus"
    }
    assert mapped_ids == gatus_ids, "Gatus and Backstage references must converge"
    assert not any("password" in str(item).lower() or "token" in str(item).lower()
                   for item in mapping["mappings"]), "mapping must not export credentials"
