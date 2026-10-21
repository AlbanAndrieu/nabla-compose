"""Read-only, ordered and fail-closed TrueNAS Catalog v2 restart plan."""
from __future__ import annotations

import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ops = runpy.run_path(str(ROOT / "scripts/truenas/restart-catalog-v2-apps.py"))


def test_gatus_separate_deferred_last_and_core_dependencies():
    apps = [
        {"id": "api", "state": "RUNNING"},
        {"id": "postgres", "state": "RUNNING"},
        {"id": "gatus", "state": "STOPPED"},
        {"id": "plex", "state": "STOPPED"},
    ]
    catalog = {"catalogRevision": "sha256:demo", "entities": [
        {"entityRef": "component:default/api", "metadata": {}, "spec": {
            "dependsOn": ["resource:default/postgresql"]}},
        {"entityRef": "resource:default/postgresql", "metadata": {}, "spec": {}},
    ]}
    identity = {"catalogRevision": "sha256:demo", "mappings": [
        {"sourceType": "compose", "sourceId": "apps/api/compose.yml#services/api",
         "entityRef": "component:default/api"},
        {"sourceType": "compose", "sourceId": "apps/postgres/compose.yml#services/db",
         "entityRef": "resource:default/postgresql"},
    ]}
    manifest = {"items": []}
    report = ops["make_plan"](apps, catalog, identity, manifest, {"plex"}, Path("/"))
    assert report["coreRestartOrder"] == ["postgres", "api"]
    assert report["nonBlockingGatus"] == ["gatus"]
    assert report["deferredLast"] == ["plex"]
    assert report["counts"]["running"] == 2
    assert report["counts"]["stopped"] == 2
    assert report["planHash"] == ops["make_plan"](
        apps, catalog, identity, manifest, {"plex"}, Path("/"))["planHash"]


def test_running_secret_gap_is_preflight_blocker_not_secret_verified():
    apps = [{"id": "api", "state": "RUNNING"}]
    catalog = {"catalogRevision": "sha256:demo", "entities": [
        {"entityRef": "component:default/api", "metadata": {}, "spec": {}}
    ]}
    mapping = {"catalogRevision": "sha256:demo", "mappings": [
        {"sourceType": "compose", "sourceId": "apps/api/compose.yml#services/api",
         "entityRef": "component:default/api"}
    ]}
    manifest = {"items": [{"app": "api"}]}
    report = ops["make_plan"](apps, catalog, mapping, manifest, set(), Path("/impossible-namespace"))
    assert report["missingRunningSecrets"] == ["api"]


def test_deferred_policy_rejects_gatus_or_critical(tmp_path: Path):
    file = tmp_path / "optional.txt"
    file.write_text("gatus\n", encoding="utf-8")
    with pytest.raises(ValueError, match="gatus"):
        ops["load_deferred"](file)
    file.write_text("vaultwarden\n", encoding="utf-8")
    with pytest.raises(ValueError, match="critical"):
        ops["load_deferred"](file)


def test_duplicate_true_nas_identifiers_fail():
    with pytest.raises(ValueError, match="duplicate"):
        ops["state_by_app"]([
            {"id": "api", "state": "RUNNING"},
            {"id": "api", "state": "STOPPED"},
        ])


def test_optional_waves_do_not_depend_on_core_secret_readiness():
    apps = [
        {"id": "api", "state": "RUNNING"},
        {"id": "gatus", "state": "STOPPED"},
        {"id": "plex", "state": "STOPPED"},
    ]
    catalog = {"catalogRevision": "sha256:test", "entities": []}
    mappings = {"catalogRevision": "sha256:test", "mappings": []}
    manifest = {"items": [{"app": "api"}]}
    report = ops["make_plan"](
        apps, catalog, mappings, manifest, {"plex"}, Path("/no-runtime-secrets")
    )
    assert report["missingRunningSecrets"] == ["api"]
    with pytest.raises(RuntimeError, match="core blocked"):
        ops["validate_wave"](report, "core")
    ops["validate_wave"](report, "gatus")
    ops["validate_wave"](report, "deferred")


def test_gatus_wave_requires_safe_state_and_its_own_secrets():
    apps = [{"id": "gatus", "state": "CRASHED"}]
    catalog = {"catalogRevision": "sha256:test", "entities": []}
    mappings = {"catalogRevision": "sha256:test", "mappings": []}
    report = ops["make_plan"](
        apps, catalog, mappings, {"items": []}, set(), Path("/")
    )
    with pytest.raises(RuntimeError, match="RUNNING or STOPPED"):
        ops["validate_wave"](report, "gatus")
    apps[0]["state"] = "STOPPED"
    report = ops["make_plan"](
        apps, catalog, mappings, {"items": [{"app": "gatus"}]}, set(),
        Path("/no-runtime-secrets"),
    )
    assert report["gatusMissingSecret"]
    with pytest.raises(RuntimeError, match="Gatus blocked"):
        ops["validate_wave"](report, "gatus")


def test_deferred_planned_workload_rejected_before_mutation():
    apps = [{"id": "plex", "state": "STOPPED"}]
    catalog = {"catalogRevision": "sha256:test", "entities": [
        {"entityRef": "component:default/plex",
         "metadata": {"labels": {"albandrieu.com/operational-state": "planned"}},
         "spec": {}},
    ]}
    mappings = {"catalogRevision": "sha256:test", "mappings": [
        {"sourceType": "compose",
         "sourceId": "apps/plex/compose.yml#services/plex",
         "entityRef": "component:default/plex"},
    ]}
    report = ops["make_plan"](
        apps, catalog, mappings, {"items": []}, {"plex"}, Path("/")
    )
    assert report["plannedOrDisabledDeferred"] == ["plex"]
    with pytest.raises(RuntimeError, match="deferred wave blocked"):
        ops["validate_wave"](report, "deferred")


def test_gatus_only_apply_never_restarts_core_and_reports_failure(monkeypatch, tmp_path):
    import sys

    globals_ = ops["main"].__globals__
    calls = []
    fake = {
        "planHash": "a" * 64,
        "states": {"api": "RUNNING", "gatus": "STOPPED"},
        "coreRestartOrder": ["api"],
        "nonBlockingGatus": ["gatus"],
        "deferredLast": [],
        "catalogRevision": "sha256:fixture",
        "counts": {},
        "missingRunningSecrets": ["api"],
        "blockedApps": [],
        "blockedCoreApps": [],
        "runningDeferredExcluded": [],
        "gatusBlocked": False,
        "gatusMissingSecret": False,
        "missingDeferredSecrets": [],
        "blockedDeferredApps": [],
        "plannedOrDisabledDeferred": [],
    }
    monkeypatch.setitem(globals_, "AUDIT_DIR", tmp_path)
    monkeypatch.setitem(globals_, "query_apps", lambda: [])
    monkeypatch.setitem(globals_, "read_json", lambda _: {})
    monkeypatch.setitem(globals_, "load_deferred", lambda: set())
    monkeypatch.setitem(globals_, "make_plan", lambda *args: fake)
    monkeypatch.setitem(globals_, "restart_one", lambda app: calls.append(("restart", app)))
    monkeypatch.setitem(globals_, "start_one", lambda app: calls.append(("start", app)))
    monkeypatch.setattr(globals_["os"], "geteuid", lambda: 0)
    monkeypatch.setattr(sys, "argv", [
        "restart-catalog-v2-apps.py", "--apply", "--include-gatus",
        "--expected-plan-hash", "a" * 64,
        "--acknowledge-downtime", ops["ACK"],
    ])
    assert ops["main"]() == 0
    assert calls == [("start", "gatus")]
    assert len(list(tmp_path.glob("catalog-v2-gatus-*.jsonl"))) == 1

    def failure(app):
        calls.append(("failed", app))
        raise RuntimeError("sensitive diagnostic not to log")

    monkeypatch.setitem(globals_, "start_one", failure)
    assert ops["main"]() == 1
    assert calls[-1] == ("failed", "gatus")
    assert len(list(tmp_path.glob("catalog-v2-gatus-*.jsonl"))) == 2


def test_broken_gatus_mapping_does_not_block_core():
    apps = [
        {"id": "api", "state": "RUNNING"},
        {"id": "gatus", "state": "RUNNING"},
    ]
    catalog = {"catalogRevision": "sha256:test", "entities": [
        {"entityRef": "component:default/gatus", "metadata": {},
         "spec": {"dependsOn": ["resource:default/missing"]}},
    ]}
    mappings = {"catalogRevision": "sha256:test", "mappings": [
        {"sourceType": "compose", "sourceId": "apps/gatus/compose.yml#services/gatus",
         "entityRef": "component:default/gatus"},
    ]}
    report = ops["make_plan"](
        apps, catalog, mappings, {"items": []}, set(), Path("/")
    )
    assert report["gatusBlocked"]
    assert report["blockedCoreApps"] == []
    ops["validate_wave"](report, "core")
    with pytest.raises(RuntimeError, match="Gatus blocked"):
        ops["validate_wave"](report, "gatus")


def test_deferred_only_apply_never_restarts_core(monkeypatch, tmp_path):
    import sys

    globals_ = ops["main"].__globals__
    calls = []
    fake = {
        "planHash": "b" * 64,
        "states": {"api": "RUNNING", "plex": "STOPPED"},
        "coreRestartOrder": ["api"],
        "nonBlockingGatus": [],
        "deferredLast": ["plex"],
        "catalogRevision": "sha256:fixture",
        "counts": {},
        "missingRunningSecrets": ["api"],
        "blockedApps": [],
        "blockedCoreApps": [],
        "runningDeferredExcluded": [],
        "gatusBlocked": False,
        "gatusMissingSecret": False,
        "missingDeferredSecrets": [],
        "blockedDeferredApps": [],
        "plannedOrDisabledDeferred": [],
    }
    monkeypatch.setitem(globals_, "AUDIT_DIR", tmp_path)
    monkeypatch.setitem(globals_, "query_apps", lambda: [])
    monkeypatch.setitem(globals_, "read_json", lambda _: {})
    monkeypatch.setitem(globals_, "load_deferred", lambda: set())
    monkeypatch.setitem(globals_, "make_plan", lambda *args: fake)
    monkeypatch.setitem(globals_, "restart_one", lambda app: calls.append(("restart", app)))
    monkeypatch.setitem(globals_, "start_one", lambda app: calls.append(("start", app)))
    monkeypatch.setattr(globals_["os"], "geteuid", lambda: 0)
    monkeypatch.setattr(sys, "argv", [
        "restart-catalog-v2-apps.py", "--apply", "--include-deferred",
        "--expected-plan-hash", "b" * 64,
        "--acknowledge-downtime", ops["ACK"],
    ])
    assert ops["main"]() == 0
    assert calls == [("start", "plex")]
