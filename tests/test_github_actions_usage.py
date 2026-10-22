"""Fast, offline contracts for the GitHub Actions budget inventory.

Never invokes GitHub CLI or creates Actions workflow runs.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/github-actions-usage.py"
SPEC = importlib.util.spec_from_file_location("github_actions_usage", SOURCE)
assert SPEC is not None and SPEC.loader is not None
usage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(usage)
SINCE = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)


def test_fetch_small_limit_is_exactly_one_page(monkeypatch):
    called = []
    def fake(path, key, paginate=True):
        called.append((path, key, paginate))
        return [{"id": n} for n in range(15)]
    monkeypatch.setattr(usage, "items", fake)
    runs = usage.recent_runs("example/repo", SINCE, 15)
    assert len(runs) == 15
    assert len(called) == 1
    assert called[0][1:] == ("workflow_runs", False)
    assert "per_page=15&page=1" in called[0][0]
    assert "created=%3E%3D2026-10-01" in called[0][0]


def test_fetch_large_limit_is_bounded_across_pages(monkeypatch):
    called = []
    def fake(path, key, paginate=True):
        called.append(path)
        page = int(path.split("page=")[-1].split("&")[0])
        return [{"id": (page - 1) * 100 + n} for n in range(100)]
    monkeypatch.setattr(usage, "items", fake)
    runs = usage.recent_runs("example/repo", SINCE, 120)
    assert [r["id"] for r in runs] == list(range(120))
    assert len(called) == 2
    assert all("per_page=100" in path for path in called)
    assert "page=1" in called[0] and "page=2" in called[1]


def test_fetch_ends_on_short_page(monkeypatch):
    called = []
    def fake(path, key, paginate=True):
        called.append(path)
        return [{"id": 1}]
    monkeypatch.setattr(usage, "items", fake)
    assert usage.recent_runs("example/repo", SINCE, 250) == [{"id": 1}]
    assert len(called) == 1


def test_empty_page_does_not_loop(monkeypatch):
    calls = []
    monkeypatch.setattr(usage, "items", lambda *a, **kw: calls.append(a) or [])
    assert usage.recent_runs("example/repo", SINCE, 150) == []
    assert len(calls) == 1


@pytest.mark.parametrize("arguments", [
    ["--days", "0"], ["--days", "-1"],
    ["--max-runs", "0"], ["--max-runs", "-50"],
])
def test_reject_invalid_limits_without_touching_network(monkeypatch, arguments):
    def forbidden(*args, **kwargs):
        pytest.fail("Must reject invalid arguments before any API call")
    monkeypatch.setattr(usage, "items", forbidden)
    monkeypatch.setattr(sys, "argv", ["github-actions-usage.py", *arguments])
    with pytest.raises(SystemExit) as error:
        usage.main()
    assert error.value.code == 2


def test_items_single_page_uses_no_paginate_flags(monkeypatch):
    commands = []
    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({
            "workflow_runs": [{"id": 99}]
        }))
    monkeypatch.setattr(usage.subprocess, "run", fake_run)
    assert usage.items("repos/example/repo/actions/runs?per_page=20",
                       "workflow_runs", paginate=False) == [{"id": 99}]
    assert "--paginate" not in commands[0]
    assert "--slurp" not in commands[0]


def test_jobs_wall_clock_is_not_a_billed_minute_claim(monkeypatch):
    job = {
        "started_at": "2026-10-22T09:00:00Z",
        "completed_at": "2026-10-22T09:02:30Z",
        "conclusion": "success",
    }
    monkeypatch.setattr(usage, "items", lambda *a, **kw: [
        job, {"conclusion": "skipped"},
    ])
    wall, skipped = usage.job_stats("example/repo", 1)
    assert wall == pytest.approx(2.5)
    assert skipped == 1


def test_api_calls_have_a_bounded_timeout(monkeypatch):
    def timeout(command, **kwargs):
        assert kwargs["timeout"] == 45
        raise subprocess.TimeoutExpired(command, 45)
    monkeypatch.setattr(usage.subprocess, "run", timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        usage.items("repos/example/repo/actions/runs", "workflow_runs", paginate=False)


def test_main_retains_good_jobs_when_artifacts_and_other_jobs_fail(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["github-actions-usage.py", "--repo", "one", "--repo", "two"])
    def recent(name, since, limit):
        return [{"id": 1, "name": "Build"}, {"id": 2, "name": "Build"}] if name.endswith("/one") else []
    def artifact_items(path, key, paginate=True):
        if "/one/" in path:
            raise subprocess.CalledProcessError(403, ["gh", "api"])
        return []
    def job(name, run_id):
        if run_id == 2:
            raise subprocess.TimeoutExpired(["gh", "api"], 45)
        return 4.5, 0
    monkeypatch.setattr(usage, "recent_runs", recent)
    monkeypatch.setattr(usage, "items", artifact_items)
    monkeypatch.setattr(usage, "job_stats", job)
    assert usage.main() == 1
    out, err = capsys.readouterr()
    assert "AlbanAndrieu/one :: Build\t1\t4.5" in out
    assert "AlbanAndrieu/two" not in out
    assert "artifacts" in err and "jobs" in err
    assert "partial API inventory" in err


def test_main_keeps_artifact_metrics_when_run_history_fails(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["github-actions-usage.py", "--repo", "one"])
    def fail_runs(*args):
        raise subprocess.TimeoutExpired(["gh", "api"], 45)
    monkeypatch.setattr(usage, "recent_runs", fail_runs)
    monkeypatch.setattr(usage, "items", lambda *a, **kw: [
        {"expired": False, "size_in_bytes": 1048576},
    ])
    assert usage.main() == 1
    out, err = capsys.readouterr()
    assert "stored artifacts\t0\t0.0\t1.0" in out
    assert "workflow runs" in err
    assert "partial API inventory" in err


def test_successful_inventory_has_zero_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["github-actions-usage.py", "--repo", "one"])
    monkeypatch.setattr(usage, "recent_runs", lambda *args: [])
    monkeypatch.setattr(usage, "items", lambda *args, **kwargs: [])
    assert usage.main() == 0
    assert "partial API inventory" not in capsys.readouterr().err
