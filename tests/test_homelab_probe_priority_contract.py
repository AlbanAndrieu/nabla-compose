import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog" / "homelab-services.json"
OVERRIDES = ROOT / "catalog" / "homelab-exposure-overrides.json"
SCHEMA = ROOT / "catalog" / "homelab-exposure-overrides.schema.json"

# fastapi-sample bootstrap order (PR #342); ranks are kept even when a service
# is absent from the catalog so later additions do not reshuffle the list.
EXPECTED_PRIORITIES = {
    "garage": 0,
    "garage-admin": 1,
    "garage-webui": 2,
    "postgresql": 3,
    "vaultwarden": 6,
    "sentry": 7,
    "prometheus": 8,
    "grafana": 9,
    "n8n": 10,
}
ABSENT_FROM_CATALOG = {"redis", "cloudflared", "pyroscope"}


def _overrides() -> list[dict]:
    return json.loads(OVERRIDES.read_text(encoding="utf-8"))["services"]


def _catalog_by_name() -> dict[str, dict]:
    services = json.loads(CATALOG.read_text(encoding="utf-8"))["services"]
    return {item["name"].casefold(): item for item in services}


def _ranked() -> dict[str, int]:
    catalog = _catalog_by_name()
    return {
        catalog[item["name"].casefold()]["id"]: item["probePriority"]
        for item in _overrides()
        if "probePriority" in item
    }


def test_probe_priority_is_a_strict_bounded_integer() -> None:
    for item in _overrides():
        if "probePriority" not in item:
            continue
        rank = item["probePriority"]
        # bool is an int subclass in Python; fastapi-sample validates strictly.
        assert type(rank) is int, f"{item['name']}: probePriority must be an integer, got {rank!r}"
        assert 0 <= rank <= 1000, f"{item['name']}: probePriority out of range: {rank}"


def test_probe_priority_ranks_are_unique() -> None:
    ranks = [item["probePriority"] for item in _overrides() if "probePriority" in item]
    duplicates = sorted({rank for rank in ranks if ranks.count(rank) > 1})
    assert not duplicates, f"duplicate probePriority ranks: {duplicates}"


def test_overrides_target_catalog_names_once() -> None:
    catalog = _catalog_by_name()
    names = [item["name"].casefold() for item in _overrides()]
    assert len(names) == len(set(names)), "duplicate override names"
    unknown = sorted(name for name in names if name not in catalog)
    assert not unknown, f"overrides target unknown catalog names: {unknown}"


def test_probe_priority_matches_fastapi_bootstrap_order() -> None:
    assert _ranked() == EXPECTED_PRIORITIES
    catalog_ids = {item["id"] for item in _catalog_by_name().values()}
    assert not ABSENT_FROM_CATALOG & catalog_ids, "rank the newly cataloged service explicitly"


def test_garage_ranks_follow_deployment_unit_probe_order() -> None:
    # PR #257 orders endpoints inside the Garage unit; probePriority is the only
    # global rank and must not contradict it.
    ranked = _ranked()
    assert ranked["garage"] < ranked["garage-admin"] < ranked["garage-webui"]


def test_overrides_validate_against_schema() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(json.loads(OVERRIDES.read_text(encoding="utf-8")), schema)


# JSON Schema treats 1.0 as an integer; the strict Python check above covers it.
@pytest.mark.parametrize("invalid", [True, False, -1, 1001, "1"])
def test_schema_rejects_invalid_probe_priority(invalid: object) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"services": [{"name": "Garage S3 API", "probePriority": invalid}]}, schema)
