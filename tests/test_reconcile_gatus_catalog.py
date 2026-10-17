"""Offline contracts for the Gatus/catalog reconciliation preview."""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/truenas/reconcile-gatus-catalog.py"
spec = importlib.util.spec_from_file_location("reconcile_gatus_catalog", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_failed_probe_does_not_mean_service_down():
    catalog = {"services": [{"id": "home-assistant"}]}
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
    # The probe URL and its token must not leak (the report note may say "secrets").
    assert "token=secret" not in str(report)
    assert "127.0.0.1:8123/private" not in str(report)
    assert report["monitors"][0]["catalog_match"]


def test_unmapped_and_duplicate_monitor_ids():
    config = {"endpoints": [
        {"name": "a", "extra-labels": {"nabla_monitor_id": "a", "nabla_service_id": "missing"}},
        {"name": "b", "extra-labels": {"nabla_monitor_id": "a", "nabla_service_id": "missing"}},
    ]}
    report = module.reconcile({"services": []}, config)
    assert report["duplicate_monitor_ids"] == ["a"]
    assert report["monitors"][0]["classification"] == "needs_service_mapping"


def test_missing_results_remain_unknown():
    config = {"endpoints": [{"name": "a", "group": "ops",
              "extra-labels": {"nabla_monitor_id": "a"}}]}
    report = module.reconcile({"services": []}, config,
                              [{"name": "a", "group": "ops", "results": []}])
    assert report["monitors"][0]["classification"] == "no_recent_evidence"


def test_canonical_topology_resolves_technical_component():
    config = {"endpoints": [{"name": "Exporter", "group": "observability",
              "extra-labels": {"nabla_monitor_id": "postgres-exporter",
                               "nabla_service_id": "postgres-exporter"}}]}
    topology = {"nodes": [{"id": "postgres-exporter"}]}
    report = module.reconcile({"services": []}, config, topology=topology)
    row = report["monitors"][0]
    assert row["mapping_source"] == "canonical_topology"
    assert row["classification"] == "not_checked"
    assert report["unresolved_monitor_ids"] == []


def test_unknown_service_remains_unresolved():
    config = {"endpoints": [{"name": "Unknown",
              "extra-labels": {"nabla_monitor_id": "unknown",
                               "nabla_service_id": "unknown"}}]}
    report = module.reconcile({"services": []}, config, topology={"nodes": []})
    assert report["unresolved_monitor_ids"] == ["unknown"]
