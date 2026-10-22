"""Real offline contracts for TrueNAS optional wave dependency ordering."""
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts/truenas/catalog_v2_restart_dependencies.py"
SPEC = importlib.util.spec_from_file_location("catalog_v2_restart_dependencies", PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
order = module.deferred_start_order


def entry(ref, *depends):
    return {"entityRefs": [ref], "dependsOn": list(depends)}


def test_dependency_order_not_alphabetical():
    entries = {
        "a-web": entry("component:default/web", "component:default/db"),
        "z-db": entry("component:default/db"),
    }
    assert order(entries, {"a-web": "STOPPED", "z-db": "STOPPED"},
                 {"a-web", "z-db"}) == (["z-db", "a-web"], [])


def test_external_provider_must_be_running():
    entries = {
        "web": entry("component:default/web", "resource:default/postgres"),
        "postgres": entry("resource:default/postgres"),
    }
    actual, blockers = order(entries, {"web": "STOPPED", "postgres": "STOPPED"}, {"web"})
    assert actual == ["web"]
    assert blockers == ["web: dependency postgres is not RUNNING"]
    assert order(entries, {"web": "STOPPED", "postgres": "RUNNING"}, {"web"}) == (["web"], [])


def test_missing_provider_blocks_deferred_wave():
    actual, blockers = order({"app": entry("component:default/app", "resource:default/missing")},
                             {"app": "STOPPED"}, {"app"})
    assert actual == ["app"]
    assert blockers == ["app: missing dependency provider for resource:default/missing"]


def test_ambiguous_provider_blocks_deferred_wave():
    entries = {
        "app": entry("component:default/app", "resource:default/db"),
        "db1": entry("resource:default/db"),
        "db2": entry("resource:default/db"),
    }
    _, blockers = order(entries, {"app": "STOPPED", "db1": "RUNNING", "db2": "RUNNING"}, {"app"})
    assert blockers == ["app: ambiguous dependency provider for resource:default/db"]


def test_cycle_blocks_deferred_wave():
    entries = {
        "a": entry("component:default/a", "component:default/b"),
        "b": entry("component:default/b", "component:default/a"),
    }
    actual, blockers = order(entries, {"a": "STOPPED", "b": "STOPPED"}, {"a", "b"})
    assert actual == []
    assert blockers == ["cycle in deferred dependency graph"]


def test_crashed_not_started_and_no_unknown_false_positive():
    entries = {"app": entry("component:default/app")}
    assert order(entries, {"app": "CRASHED"}, {"app"}) == ([], [])
    assert order(entries, {"app": "STOPPED"}, {"app"}) == (["app"], [])


def test_missing_inventory_entry_is_a_blocker():
    _, blockers = order({}, {"app": "STOPPED"}, {"app"})
    assert blockers == ["app: missing inventory entry"]


def test_deterministic_independent_apps():
    entries = {"z": entry("component:default/z"), "a": entry("component:default/a")}
    assert order(entries, {"a": "STOPPED", "z": "STOPPED"}, {"z", "a"}) == (["a", "z"], [])
