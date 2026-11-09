"""Offline contracts for the impacted TrueNAS App redeploy planner."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/redeploy-impacted-apps.py"
SPEC = importlib.util.spec_from_file_location("redeploy_impacted_apps", SCRIPT)
assert SPEC and SPEC.loader
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)


def _row(app: str, **overrides: object) -> dict:
    row = {
        "app": app, "runtimeId": app, "sourcePath": f"apps/{app}/compose.yml",
        "serviceIds": [app], "status": "active", "statusError": None,
        "mappingError": None, "manual": False, "initializationEligible": True,
    }
    row.update(overrides)
    return row


def test_only_non_markdown_app_files_mark_an_app_changed() -> None:
    assert planner.changed_app_dirs([
        "apps/kafka/compose.yml", "apps/kafka/README.md", "apps/gatus/README.md",
        "apps/fastapi-sample", "docs/roadmap.md",
    ]) == {"kafka", "fastapi-sample"}


def test_app_dependencies_come_from_catalog_depends_on() -> None:
    catalog = json.loads((ROOT / "catalog/services.json").read_text(encoding="utf-8"))
    topology = json.loads((ROOT / "catalog/service-topology.json").read_text(encoding="utf-8"))
    rows = planner.declared_apps(catalog, root=ROOT)
    deps = planner.app_dependencies(topology, rows)
    assert {"kafka", "clickhouse"} <= deps["akvorado"]


def test_plan_orders_providers_first_and_explains_every_skip() -> None:
    rows = [_row(app) for app in ("kafka", "akvorado", "bar", "baz", "sample", "langfuse")]
    rows.append(_row("idea", status="planned", initializationEligible=False))
    deps = {"akvorado": {"kafka"}, "langfuse": {"kafka"}, "kafka": set()}
    states = {app: "RUNNING" for app in ("kafka", "akvorado", "baz", "sample", "langfuse")}
    states["bar"] = "STOPPED"

    plan = planner.build_plan(
        {"akvorado", "kafka", "bar", "baz", "sample", "ghost", "idea"},
        rows, deps, states, lambda app, source: app != "baz",
    )

    assert plan["redeploy"] == ["kafka", "akvorado"]
    assert plan["dedicated"] == ["sample (scripts/truenas/update-fastapi-sample.sh)"]
    assert plan["watch"] == ["langfuse"]
    assert plan["blocked"] is None
    assert plan["skipped"] == [
        "bar (STOPPED, left as is)",
        "baz (its Custom App config does not include this checkout's Compose file)",
        "ghost (not in the service catalog)",
        "idea (catalog status planned)",
    ]


def test_dependency_cycle_blocks_the_plan() -> None:
    plan = planner.build_plan(
        {"a", "b"}, [_row("a"), _row("b")], {"a": {"b"}, "b": {"a"}},
        {"a": "RUNNING", "b": "RUNNING"}, lambda app, source: True,
    )
    assert plan["redeploy"] == []
    assert plan["blocked"].startswith("dependency cycle")


@pytest.mark.parametrize(("status", "problem"), [
    ("Up 3 hours (healthy)", None),
    ("Up 2 minutes", None),
    ("Exited (0) 1 hour ago", None),
    ("Up 5 seconds (health: starting)", "health: starting"),
    ("Up 3 hours (unhealthy)", "unhealthy"),
    ("Restarting (1) 4 seconds ago", "restarting"),
    ("Exited (137) 2 minutes ago", "exited"),
])
def test_container_status_classification(status: str, problem: str | None) -> None:
    assert planner.container_problem(status) == problem


def test_apply_restarts_a_dependent_only_when_it_turned_unhealthy(capsys) -> None:
    redeployed: list[str] = []
    probes = {"kafka": ["health: starting", None]}

    def health(app: str) -> str | None:
        if app in probes and probes[app]:
            return probes[app].pop(0)
        if app == "sentry" and "sentry" not in redeployed:
            return "sentry-web-1 unhealthy"
        return None

    rc = planner.apply(
        {"redeploy": ["kafka", "akvorado"], "watch": ["langfuse", "sentry"]},
        {"langfuse": {"kafka"}, "sentry": {"kafka"}, "n8n": {"sentry"}},
        {app: "RUNNING" for app in ("kafka", "akvorado", "langfuse", "sentry", "n8n")},
        redeployed.append, health, sleep=lambda _: None,
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert redeployed == ["kafka", "akvorado", "sentry"]
    assert "OK: dependent langfuse healthy, not restarted" in out
    assert "RESTART: dependent sentry unhealthy (sentry-web-1 unhealthy)" in out
    assert "OK: dependent n8n healthy, not restarted" in out


def test_apply_stops_at_the_first_app_that_does_not_converge(capsys) -> None:
    redeployed: list[str] = []
    rc = planner.apply(
        {"redeploy": ["kafka", "akvorado"], "watch": ["langfuse"]},
        {"akvorado": {"kafka"}, "langfuse": {"kafka"}},
        {"kafka": "RUNNING", "akvorado": "RUNNING", "langfuse": "RUNNING"},
        redeployed.append, lambda app: "CRASHED", sleep=lambda _: None,
    )
    assert rc == 1
    assert redeployed == ["kafka"]
    assert "FAIL: kafka not healthy after app.redeploy (CRASHED); stopped before: akvorado" in (
        capsys.readouterr().out
    )
