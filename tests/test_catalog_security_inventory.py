"""Catalog v2 identity and relationship contracts for discovery/security tools."""
from __future__ import annotations
from pathlib import Path
import json
import yaml

ROOT = Path(__file__).resolve().parents[1]


def catalog() -> dict[str, dict]:
    data = json.loads((ROOT / "catalog/generated/entities.json").read_text(encoding="utf-8"))
    return {ent["entityRef"]: ent for ent in data["entities"]}


def test_discovery_stack_uses_single_declared_entity_for_shared_stores() -> None:
    entities = catalog()
    assert "resource:default/clickhouse" in entities
    assert "resource:default/kafka" in entities
    assert "resource:default/neo4j-security" in entities
    assert entities["component:default/cartography"]["spec"]["dependsOn"] == [
        "resource:default/neo4j-security"
    ]
    # ntopng Community has no ClickHouse flow backend (Enterprise M+ only).
    assert "dependsOn" not in entities["component:default/ntopng"]["spec"]
    assert entities["component:default/scanopy"]["spec"]["dependsOn"] == [
        "resource:default/postgresql"
    ]
    assert entities["component:default/dsomm-baseline"]["spec"]["subcomponentOf"] == (
        "component:default/dsomm"
    )


def test_akvorado_active_and_monitored_through_its_console() -> None:
    entities = catalog()
    names = {
        "akvorado-orchestrator", "akvorado-inlet", "akvorado-outlet", "akvorado-console"
    }
    for name in names:
        component = entities[f"component:default/{name}"]
        assert component["metadata"]["labels"]["albandrieu.com/operational-state"] == "active"
        assert component["spec"]["system"] == "system:default/nabla-homelab"
        assert set(component["spec"].get("dependsOn", [])) <= {
            "resource:default/clickhouse", "resource:default/kafka"
        }
    homarr = json.loads((ROOT / "apps/homarr/generated/apps.json").read_text())
    apps = {item["id"]: item for item in homarr["applications"]}
    assert names <= set(apps)
    # Only the console has a UI worth a Homarr tile.
    assert {name for name in names if apps[name]["syncEligible"]} == {"akvorado-console"}
    gatus = yaml.safe_load((ROOT / "apps/gatus/config/config.yml").read_text())
    monitored = {e.get("extra-labels", {}).get("nabla_service_id") for e in gatus["endpoints"]}
    assert names & monitored == {"akvorado-console"}


def test_backstage_compose_mapping_is_declared_once() -> None:
    entities = catalog()
    for app in ("akvorado", "clickhouse", "scanopy", "ntopng", "dsomm"):
        compose = yaml.safe_load((ROOT / "apps" / app / "compose.yml").read_text())
        for svc in compose["services"].values():
            labels = svc.get("labels") or {}
            if "com.albandrieu.nabla.entity-ref" not in labels:
                continue
            ref = labels["com.albandrieu.nabla.entity-ref"]
            assert ref in entities
    assert len(entities) == len(set(entities))
