"""Offline contracts for the Gatus/catalog reconciliation preview."""
import importlib.util
from datetime import UTC, datetime, timedelta
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
    now = datetime.now(UTC)
    statuses = [{"name": "Home Assistant", "group": "home",
                 "results": [{"timestamp": now.isoformat(), "success": False}]}]
    report = module.reconcile(catalog, config, statuses, now=now)
    assert report["monitors"][0]["classification"] == "investigate_probe_not_service_down"
    assert report["monitors"][0]["probe_verdict"] == "FAIL"
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
    source = yaml.safe_load((root / "config/monitoring/gatus-endpoints.yml").read_text())
    monitors = {
        endpoint["extra-labels"]["nabla_monitor_id"]: endpoint
        for endpoint in source["endpoints"]
    }
    for service_id in ("pfsense", "postgresql", "truenas"):
        assert monitors[service_id]["extra-labels"]["nabla_service_id"] == service_id


def _one_monitor() -> tuple[dict, dict]:
    return (
        {"entities": [_entity("gatus-service")]},
        {"endpoints": [{
            "name": "Gatus Service", "group": "ops", "url": "https://private.invalid",
            "extra-labels": {
                "nabla_monitor_id": "gatus-service",
                "nabla_service_id": "gatus-service",
            },
        }]},
    )


def test_reconciliation_matches_gatus_freshness_and_latest_sample():
    catalog, config = _one_monitor()
    now = datetime.now(UTC)
    earlier = (now - timedelta(seconds=250)).isoformat()
    recent = (now - timedelta(seconds=10)).isoformat()
    statuses = [{"name": "Gatus Service", "group": "ops", "results": [
        {"timestamp": earlier, "success": False, "error": "SECRET=PRIVATE"},
        {"timestamp": recent, "success": True},
    ]}]
    report = module.reconcile(catalog, config, statuses, now=now)
    check = report["monitors"][0]
    assert check["evidence"] == "probe_success"
    assert check["probe_verdict"] == "PASS"
    assert report["probe_verdict_counts"]["PASS"] == 1
    assert "PRIVATE" not in str(report)


def test_reconciliation_expired_success_is_unverified():
    catalog, config = _one_monitor()
    now = datetime.now(UTC)
    statuses = [{"name": "Gatus Service", "group": "ops", "results": [{
        "timestamp": (now - timedelta(minutes=10)).isoformat(),
        "success": True,
    }]}]
    report = module.reconcile(catalog, config, statuses, now=now)
    check = report["monitors"][0]
    assert check["probe_verdict"] == "UNVERIFIED"
    assert check["probe_reason"] == "stale_or_invalid_timestamp"
    assert check["classification"] == "no_recent_evidence"


def test_reconciliation_401_403_are_not_service_down():
    catalog, config = _one_monitor()
    now = datetime.now(UTC)
    for error in ("HTTP 401 API_KEY=SECRET", "HTTP 403 private"):
        statuses = [{"name": "Gatus Service", "group": "ops", "results": [{
            "timestamp": now.isoformat(), "success": False, "error": error,
        }]}]
        report = module.reconcile(catalog, config, statuses, now=now)
        check = report["monitors"][0]
        assert check["evidence"] == "probe_access_denied"
        assert check["probe_verdict"] == "DENIED"
        assert check["classification"] == "access_denied_not_service_down"
        assert "SECRET" not in str(report)


def test_reconciliation_does_not_assume_unique_runtime_or_declared_identity():
    catalog, config = _one_monitor()
    now = datetime.now(UTC)
    sample = {"name": "Gatus Service", "group": "ops", "results": [{
        "timestamp": now.isoformat(), "success": True,
    }]}
    duplicated_runtime = module.reconcile(catalog, config, [sample, sample], now=now)
    check = duplicated_runtime["monitors"][0]
    assert check["probe_verdict"] == "UNVERIFIED"
    assert check["probe_reason"] == "duplicate_runtime_monitor"

    duplicated_config = {"endpoints": [config["endpoints"][0], {
        **config["endpoints"][0],
        "extra-labels": {
            "nabla_monitor_id": "other-monitor",
            "nabla_service_id": "gatus-service",
        },
    }]}
    duplicated_declared = module.reconcile(catalog, duplicated_config, [sample], now=now)
    assert all(row["probe_verdict"] == "UNVERIFIED"
               for row in duplicated_declared["monitors"])
    assert all(row["probe_reason"] == "duplicate_declared_monitor"
               for row in duplicated_declared["monitors"])


def test_reconciliation_not_run_missing_and_invalid_results():
    catalog, config = _one_monitor()
    now = datetime.now(UTC)
    absent = module.reconcile(catalog, config)
    assert absent["monitors"][0]["probe_verdict"] == "NOT_RUN"
    missing = module.reconcile(catalog, config, [], now=now)
    assert missing["monitors"][0]["probe_verdict"] == "UNVERIFIED"
    invalid = module.reconcile(catalog, config, [{
        "name": "Gatus Service", "group": "ops",
        "results": [{"timestamp": now.isoformat(), "success": "true"}],
    }], now=now)
    assert invalid["monitors"][0]["probe_reason"] == "invalid_success_value"
    assert invalid["monitors"][0]["probe_verdict"] == "UNVERIFIED"


def test_reconciliation_counts_unmatched_runtime_without_echoing_private_fields():
    catalog, config = _one_monitor()
    now = datetime.now(UTC)
    report = module.reconcile(catalog, config, [{
        "name": "Unreviewed", "group": "private",
        "results": [{"timestamp": now.isoformat(), "success": True,
                     "message": "SECRET-CREDENTIAL"}],
    }], now=now)
    assert report["unmatched_runtime"] == 1
    assert "SECRET-CREDENTIAL" not in str(report)
