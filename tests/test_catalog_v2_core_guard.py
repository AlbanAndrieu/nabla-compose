"""Local pure-function contracts for TrueNAS core restart dependency safety."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SOURCE = (Path(__file__).resolve().parents[1] /
          "scripts/truenas/catalog_v2_restart_dependencies.py")
spec = importlib.util.spec_from_file_location("catalog_v2_restart_dependencies", SOURCE)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
core = module.core_dependency_blockers
optional = module.deferred_start_order


def row(entity: str, *depends: str) -> dict:
    return {"entityRefs": [entity], "dependsOn": list(depends)}


def test_running_core_with_running_provider_passes():
    entries = {"api": row("component:default/api", "resource:default/db"),
               "postgres": row("resource:default/db")}
    assert core(entries, {"api": "RUNNING", "postgres": "RUNNING"},
                ["postgres", "api"]) == []


@pytest.mark.parametrize("state", ["STOPPED", "CRASHED", "ERROR", "UNKNOWN"])
def test_core_rejects_inactive_provider(state):
    entries = {"api": row("component:default/api", "resource:default/db"),
               "postgres": row("resource:default/db")}
    assert core(entries, {"api": "RUNNING", "postgres": state}, ["api"]) == [
        "api: dependency postgres is not RUNNING"
    ]


def test_core_rejects_missing_provider_without_guessing():
    entries = {"api": row("component:default/api", "resource:default/missing")}
    assert core(entries, {"api": "RUNNING"}, ["api"]) == [
        "api: missing dependency provider for resource:default/missing"
    ]


def test_core_rejects_ambiguous_provider():
    entries = {"api": row("component:default/api", "resource:default/db"),
               "postgres": row("resource:default/db"),
               "shadow": row("resource:default/db")}
    assert core(entries, {app: "RUNNING" for app in entries}, ["api"]) == [
        "api: ambiguous dependency provider for resource:default/db"
    ]


def test_core_rejects_selected_app_that_is_not_running():
    assert core({"api": row("component:default/api")},
                {"api": "STOPPED"}, ["api"]) == [
        "api: selected core App is not RUNNING"
    ]


def test_core_rejects_missing_inventory_row():
    assert core({}, {"api": "RUNNING"}, ["api"]) == [
        "api: missing inventory entry"
    ]


def test_core_missing_relation_does_not_invent_dependency():
    assert core({"api": row("component:default/api")},
                {"api": "RUNNING"}, ["api"]) == []


def test_core_gatus_does_not_become_part_of_selected_wave():
    entries = {"api": row("component:default/api", "component:default/gatus"),
               "gatus": row("component:default/gatus")}
    assert core(entries, {"api": "RUNNING", "gatus": "STOPPED"}, ["api"]) == [
        "api: dependency gatus is not RUNNING"
    ]


def test_core_blockers_deduplicated_and_sorted():
    entries = {"z": row("component:default/z", "resource:default/b"),
               "a": row("component:default/a", "resource:default/a")}
    assert core(entries, {"z": "RUNNING", "a": "RUNNING"},
                ["z", "z", "a"]) == [
        "a: missing dependency provider for resource:default/a",
        "z: missing dependency provider for resource:default/b",
    ]


def test_optional_order_is_unchanged():
    entries = {"web": row("component:default/web", "resource:default/db"),
               "db": row("resource:default/db")}
    assert optional(entries, {"web": "STOPPED", "db": "STOPPED"},
                    {"web", "db"}) == (["db", "web"], [])
