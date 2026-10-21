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
