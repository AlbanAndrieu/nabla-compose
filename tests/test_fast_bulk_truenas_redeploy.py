"""No-network contracts for parallel TrueNAS image refresh/redeploy."""
from __future__ import annotations

import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
module = runpy.run_path(str(ROOT / "scripts/truenas/fast-bulk-redeploy-apps.py"))
make_plan = module["make_plan"]


def apps():
    return [
        {"id": "postgres", "name": "postgres", "state": "RUNNING"},
        {"id": "redis", "name": "redis", "state": "RUNNING"},
        {"id": "gatus", "name": "gatus", "state": "RUNNING"},
        {"id": "openwebui", "name": "openwebui", "state": "RUNNING"},
        {"id": "wordpress", "name": "wordpress", "state": "STOPPED"},
    ]


def test_default_batch_never_redeploys_core_or_stopped():
    report = make_plan(apps(), "applications", 6)
    assert report["selectedCount"] == 2
    assert report["waves"] == [
        {"name": "applications", "apps": ["gatus", "openwebui"]},
    ]
    assert {"postgres", "redis", "wordpress"} <= set(report["excluded"])
    assert report["upgradesChartOrPinnedTag"] is False
    assert len(report["planHash"]) == 64


def test_explicit_all_fleet_batches_core_before_apps():
    report = make_plan(apps(), "all", 8)
    assert report["waves"] == [
        {"name": "foundation", "apps": ["postgres", "redis"]},
        {"name": "applications", "apps": ["gatus", "openwebui"]},
    ]
    assert report["parallelism"] == 8
    assert report["excluded"] == ["wordpress"]


@pytest.mark.parametrize("bad", [
    [{"id": "bad;echo", "state": "RUNNING"}],
    [{"id": "../secret", "state": "RUNNING"}],
    [{"id": "postgres", "name": "redis", "state": "RUNNING"}],
    [{"id": "redis", "state": "RUNNING"},
     {"id": "redis", "state": "STOPPED"}],
    ["not-a-dict"],
])
def test_unsafe_app_inventory_fails_closed(bad):
    with pytest.raises(ValueError):
        make_plan(bad, "all", 4)


def test_plan_hash_catches_stopped_or_running_drift():
    old = make_plan(apps(), "all", 8)["planHash"]
    changed = apps()
    changed[-1]["state"] = "RUNNING"
    assert make_plan(changed, "all", 8)["planHash"] != old


@pytest.mark.parametrize("number", [0, 17, -1])
def test_rejects_out_of_bounds_concurrency(number):
    with pytest.raises(ValueError):
        make_plan(apps(), "all", number)


def test_default_check_never_calls_mutation(monkeypatch, capsys):
    main = module["main"]
    g = main.__globals__
    monkeypatch.setitem(g, "query", apps)
    monkeypatch.setitem(g, "redeploy",
                        lambda *a: pytest.fail("unexpected middleware mutation"))
    assert main(["--check", "--scope", "all"]) == 0
    assert "planHash" in capsys.readouterr().out


def test_apply_denied_without_acknowledgement(monkeypatch):
    main = module["main"]
    monkeypatch.setitem(main.__globals__, "query",
                        lambda: pytest.fail("should never query middleware"))
    with pytest.raises(SystemExit) as exc:
        main(["--apply", "--scope", "all"])
    assert exc.value.code == 2


def test_successful_parallel_waves_verify_before_next_wave(monkeypatch):
    execute = module["execute"]
    g = execute.__globals__
    completed = []
    def redeploy(app):
        completed.append("update:" + app)
    def verify(app):
        if app in ("gatus", "openwebui"):
            assert {"verify:postgres", "verify:redis"} <= set(completed)
        completed.append("verify:" + app)
    monkeypatch.setitem(g, "redeploy", redeploy)
    monkeypatch.setitem(g, "verify", verify)
    assert execute(make_plan(apps(), "all", 4)) == 0
    assert len(completed) == 8


def test_failure_in_foundation_blocks_application_wave(monkeypatch):
    execute = module["execute"]
    g = execute.__globals__
    calls = []
    def fail_core(app):
        calls.append(app)
        if app == "postgres":
            raise RuntimeError("no database")
    monkeypatch.setitem(g, "redeploy", fail_core)
    monkeypatch.setitem(g, "verify",
                        lambda app: pytest.fail("no verification after failure"))
    assert execute(make_plan(apps(), "all", 3)) == 1
    assert calls and set(calls) <= {"postgres", "redis"}


def test_empty_fleet_does_not_call_midclt(monkeypatch):
    monkeypatch.setitem(module["execute"].__globals__, "redeploy",
                        lambda *_: pytest.fail("no app should run"))
    assert module["execute"](make_plan([], "all", 8)) == 0
