"""V2 TrueNAS restart planner never mutates runtime or guesses Vaultwarden readiness."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts/truenas/plan-catalog-v2-restart.py"
SPEC = importlib.util.spec_from_file_location("plan_catalog_v2_restart", PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def fixtures():
    entities = {"catalogRevision": "sha256:test", "entities": [
        {"entityRef": "component:default/alpha",
         "metadata": {"labels": {"albandrieu.com/operational-state": "active"}},
         "spec": {"dependsOn": ["resource:default/postgresql"]}},
        {"entityRef": "resource:default/postgresql", "metadata": {}, "spec": {}},
    ]}
    mapping = {"catalogRevision": "sha256:test", "mappings": [
        {"sourceType": "compose", "sourceId": "apps/alpha/compose.yml#services/api",
         "entityRef": "component:default/alpha"}
    ]}
    secrets = {"items": [{"app": "alpha"}]}
    return entities, mapping, secrets


def test_running_first_and_secret_lookups_are_not_guessed():
    catalog, mappings, secrets = fixtures()
    result = module.plan(catalog, mappings, secrets, [
        {"name": "alpha", "state": "RUNNING"},
        {"name": "beta", "state": "STOPPED"},
    ])
    assert result["counts"] == {"running": 1, "other": 1, "blocked": 0, "unmapped": 1}
    item = result["waveRunning"][0]
    assert item["entityRefs"] == ["component:default/alpha"]
    assert item["dependsOn"] == ["resource:default/postgresql"]
    assert item["runtimeSecretFile"] == "not-checked"
    assert item["vaultwardenItemVerified"] is False


def test_bad_revision_fails_closed():
    catalog, mappings, secrets = fixtures()
    mappings["catalogRevision"] = "sha256:different"
    with pytest.raises(ValueError, match="catalogRevision"):
        module.plan(catalog, mappings, secrets, [])


def test_missing_relationship_is_blocked():
    catalog, mappings, secrets = fixtures()
    catalog["entities"] = catalog["entities"][:1]
    result = module.plan(catalog, mappings, secrets, [{"name": "alpha", "state": "RUNNING"}])
    assert result["counts"]["blocked"] == 1
