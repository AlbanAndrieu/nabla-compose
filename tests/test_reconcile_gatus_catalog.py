"""Offline contracts for the Gatus/catalog reconciliation preview."""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/truenas/reconcile-gatus-catalog.py"
spec = importlib.util.spec_from_file_location("reconcile_gatus_catalog", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def _entity(name: str, kind: str = "Component") -> dict:
    return {"kind": kind, "metadata": {"name": name}}


def test_failed_probe_does_not_mean_service_down():
    catalog = {"entities": [_entity("home-assistant")]}
    config = {"endpoints": [{
        "name": "Home Assistant", "group": "home",
        "url": "http://127.0.0.1:8123/private?token=secret",
        "extra-labels": {
            "nabla_monitor_id": "home-assistant",
            "nabla_service_id": "home-assistant",
        },
    }]}
    statuses = [{"name": "Home Assistant", "group": "home",
                 "results": [{"success": False}]}]
    report = module.reconcile(catalog, config, statuses)
    assert report["monitors"][0]["classification"] == "investigate_probe_not_service_down"
    assert "token=secret" not in str(report)
    assert "127.0.0.1:8123/private" not in str(report)
    assert report["monitors"][0]["mapping_source"] == "backstage"


def test_duplicate_and_unknown_monitor_ids():
    config = {"endpoints": [
        {"name": "a", "extra-labels": {"nabla_monitor_id": "a", "nabla_service_id": "missing"}},
        {"name": "b", "extra-labels": {"nabla_monitor_id": "a", "nabla_service_id": "missing"}},
    ]}
    report = module.reconcile({"entities": []}, config)
    assert report["duplicate_monitor_ids"] == ["a"]
    assert report["monitors"][0]["classification"] == "needs_service_mapping"


def test_missing_results_remain_unknown():
    config = {"endpoints": [{"name": "a", "group": "ops",
              "extra-labels": {"nabla_monitor_id": "a"}}]}
    report = module.reconcile({"entities": []}, config,
                              [{"name": "a", "group": "ops", "results": []}])
    assert report["monitors"][0]["classification"] == "no_recent_evidence"


def test_backstage_component_resolves_technical_service():
    config = {"endpoints": [{"name": "Exporter", "group": "observability",
              "extra-labels": {"nabla_monitor_id": "postgres-exporter",
                               "nabla_service_id": "postgres-exporter"}}]}
    report = module.reconcile(
        {"entities": [_entity("postgres-exporter")]}, config
    )
    row = report["monitors"][0]
    assert row["mapping_source"] == "backstage"
    assert row["classification"] == "not_checked"
    assert report["unresolved_monitor_ids"] == []


def test_unknown_service_remains_unresolved():
    config = {"endpoints": [{"name": "Unknown",
              "extra-labels": {"nabla_monitor_id": "unknown",
                               "nabla_service_id": "unknown"}}]}
    report = module.reconcile({"entities": []}, config)
    assert report["unresolved_monitor_ids"] == ["unknown"]


def test_critical_monitor_ids_reconcile_with_backstage_resources():
    import yaml

    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "apps/gatus/config/config.yml").read_text())
    entries = module.load_backstage_entities(
        [root / "catalog/catalog-info.yaml"]
    )
    resources = {
        entity["metadata"]["name"]
        for entity in entries
        if entity["kind"] == "Resource"
    }
    monitors = {
        entry["extra-labels"]["nabla_monitor_id"]: entry
        for entry in config["endpoints"]
        if "nabla_monitor_id" in entry.get("extra-labels", {})
    }
    for service_id in ("pfsense", "postgresql", "truenas"):
        assert service_id in resources
        assert monitors[service_id]["extra-labels"]["nabla_service_id"] == service_id
    rules = (root / "apps/prometheus/rules/nabla-service.rules.yml").read_text()
    assert 'nabla_service_id!=""' in rules


def test_critical_monitor_ids_come_from_backstage_refs():
    import yaml

    root = Path(__file__).resolve().parents[1]
    static = yaml.safe_load((root / "catalog/service-consumers.static.yml").read_text())
    overrides = {
        entry["entityRef"].split("/")[-1]: entry
        for entry in static["monitoring"]["overrides"]
    }
    for service_id in ("pfsense", "postgresql", "truenas"):
        assert overrides[service_id]["entityRef"] == f"resource:default/{service_id}"
