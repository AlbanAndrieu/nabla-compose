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

@pytest.mark.parametrize("bad", ["../../secrets", "repo/name", "repo?per_page=1000", "..", ".", "x\nINJECT"])
def test_validate_component_rejects_api_path_injection(bad):
    with pytest.raises(ValueError, match="invalid GitHub"):
        usage.validate_component(bad)


@pytest.mark.parametrize("good", ["nabla-compose", ".github", "repo_name", "Nabla.Site-1"])
def test_validate_component_accepts_real_repo_names(good):
    assert usage.validate_component(good) == good


@pytest.mark.parametrize("args", [
    ["--owner", "owner/name"], ["--repo", "../other"],
    ["--max-runs", "1001"],
])
def test_main_rejects_dangerous_inputs_before_api_call(monkeypatch, args):
    monkeypatch.setattr(usage, "items", lambda *a, **kw: pytest.fail("API called"))
    monkeypatch.setattr(sys, "argv", ["github-actions-usage.py", *args])
    with pytest.raises(SystemExit) as info:
        usage.main()
    assert info.value.code == 2


@pytest.mark.parametrize("payload", [
    "[]", "null", "{}", '{"workflow_runs": null}',
    '{"workflow_runs": {}}', '{"workflow_runs": [42]}',
])
def test_api_response_missing_or_invalid_envelope_is_not_zero_usage(monkeypatch, payload):
    monkeypatch.setattr(usage.subprocess, "run", lambda command, **kw:
                        subprocess.CompletedProcess(command, 0, stdout=payload))
    with pytest.raises(ValueError, match="invalid GitHub API"):
        usage.items("repos/example/repo/actions/runs", "workflow_runs", paginate=False)


def test_api_invalid_pagination_envelope_never_claims_empty_result(monkeypatch):
    monkeypatch.setattr(usage.subprocess, "run", lambda command, **kw:
                        subprocess.CompletedProcess(command, 0, stdout='{"jobs":[]}'))
    with pytest.raises(ValueError, match="pagination envelope"):
        usage.items("repos/example/repo/actions/runs", "workflow_runs", paginate=True)


def test_timeval_rejects_naive_or_invalid_timestamp():
    for raw in [123, "2026-10-22T08:00:00", "not-a-date"]:
        with pytest.raises(ValueError):
            usage.timeval(raw)
    assert usage.timeval(None) is None
    assert usage.timeval("2026-10-22T08:00:00Z").tzinfo is not None


def test_safe_label_prevents_log_and_terminal_injection():
    assert usage.safe_label("normal\nmalicious\x1b[31m") == "normal?malicious?[31m"
    assert "\n" not in usage.safe_label("safe\nunsafe")
    assert len(usage.safe_label("x" * 300)) == 140


def test_invalid_job_timestamp_means_partial_metrics_not_zero(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["github-actions-usage.py", "--repo", "one"])
    monkeypatch.setattr(usage, "recent_runs", lambda *args: [{"id": 4, "name": "Bad job"}])
    def fake_items(path, key, paginate=True):
        return [{"started_at": "2026-10-22T08:00:00", "completed_at": "2026-10-22T09:00:00Z"}] if key == "jobs" else []
    monkeypatch.setattr(usage, "items", fake_items)
    assert usage.main() == 1
    out, err = capsys.readouterr()
    assert "partial API inventory" in err and "Bad job" in err
    assert "0.0" not in out


@pytest.mark.parametrize("value", [0, -1, True, False, "", "1/../../other",
                                   "01?per_page=1000", 1.5, None,
                                   "9223372036854775808", {}, []])
def test_invalid_run_id_fails_closed(value):
    with pytest.raises(ValueError, match="invalid GitHub workflow run id"):
        usage.valid_run_id(value)


@pytest.mark.parametrize("value", [1, "123", 9223372036854775807])
def test_valid_run_id(value):
    assert usage.valid_run_id(value) == int(value)


@pytest.mark.parametrize("value", [-1, True, False, None, 1.5, "-5", "1.2",
                                   "15MiB", "9223372036854775808", {}, []])
def test_invalid_artifact_bytes_fails_closed(value):
    with pytest.raises(ValueError, match="invalid GitHub artifact size"):
        usage.artifact_bytes(value)


@pytest.mark.parametrize("value", [0, 1024, "2048", 9223372036854775807])
def test_valid_artifact_bytes(value):
    assert usage.artifact_bytes(value) == int(value)


def test_invalid_run_id_does_not_block_valid_job_metrics(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["github-actions-usage.py", "--repo", "one"])
    monkeypatch.setattr(usage, "recent_runs", lambda *args: [
        {"id": "44/../../secrets", "name": "Unsafe"},
        {"id": 1, "name": "Build"},
    ])
    monkeypatch.setattr(usage, "items", lambda *args, **kwargs: [])
    recorded = []
    def fake_job(name, run_id):
        recorded.append(run_id)
        return (2.0, 0)
    monkeypatch.setattr(usage, "job_stats", fake_job)
    assert usage.main() == 1
    stdout, stderr = capsys.readouterr()
    assert recorded == [1]
    assert " :: Build\t1\t2.0" in stdout
    assert "workflow run identity" in stderr
    assert "metrics incomplete" in stderr


def test_invalid_artifact_size_is_partial_not_negative_usage(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["github-actions-usage.py", "--repo", "one"])
    monkeypatch.setattr(usage, "recent_runs", lambda *args: [
        {"id": 1, "name": "Build"},
    ])
    monkeypatch.setattr(usage, "items", lambda *args, **kwargs: [
        {"expired": False, "size_in_bytes": -1024},
    ])
    monkeypatch.setattr(usage, "job_stats", lambda *args: (2.0, 0))
    assert usage.main() == 1
    stdout, stderr = capsys.readouterr()
    assert " :: Build\t1\t2.0" in stdout
    assert "stored artifacts" not in stdout
    assert "artifacts" in stderr


def test_job_stats_rejects_invalid_id_before_any_api_request(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid run id must never construct an API request")
    monkeypatch.setattr(usage, "items", forbidden)
    with pytest.raises(ValueError, match="invalid GitHub workflow run id"):
        usage.job_stats("sample/repo", "../runs?all=true")


def test_valid_artifact_metrics_survive_later_corrupted_artifact(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["github-actions-usage.py", "--repo", "one"])
    monkeypatch.setattr(usage, "recent_runs", lambda *args: [])
    monkeypatch.setattr(usage, "items", lambda *args, **kwargs: [
        {"expired": False, "size_in_bytes": 1048576},
        {"expired": False, "size_in_bytes": "invalid"},
    ])
    assert usage.main() == 1
    stdout, stderr = capsys.readouterr()
    assert "stored artifacts\t0\t0.0\t1.0" in stdout
    assert "metrics incomplete" in stderr


@pytest.mark.parametrize("start,end", [
    ("2026-10-22T09:00:00Z", "2026-10-22T08:00:00Z"),
    ("2026-10-22T09:00:00Z", None),
    (None, "2026-10-22T09:00:00Z"),
])
def test_job_timing_inconsistencies_mark_inventory_partial(monkeypatch, start, end):
    monkeypatch.setattr(usage, "items", lambda *_: [{
        "started_at": start, "completed_at": end,
    }])
    with pytest.raises(ValueError):
        usage.job_stats("owner/repo", 1)


def test_skipped_job_without_timestamps_is_not_an_error(monkeypatch):
    monkeypatch.setattr(usage, "items", lambda *_: [{"conclusion": "skipped"}])
    assert usage.job_stats("owner/repo", 1) == (0, 1)


def test_zero_duration_job_is_allowed(monkeypatch):
    monkeypatch.setattr(usage, "items", lambda *_: [{
        "started_at": "2026-10-22T09:00:00Z",
        "completed_at": "2026-10-22T09:00:00Z",
    }])
    assert usage.job_stats("owner/repo", 1) == (0, 0)


def test_duplicate_repository_selection_only_calls_api_once(monkeypatch, capsys):
    requested = []
    monkeypatch.setattr(usage, "recent_runs", lambda name, since, limit:
                        requested.append(name) or [])
    monkeypatch.setattr(usage, "items", lambda *args, **kwargs: [])
    monkeypatch.setattr(sys, "argv", [
        "github-actions-usage.py", "--repo", "foo", "--repo", "foo",
        "--repo", "bar", "--repo", "foo",
    ])
    assert usage.main() == 0
    assert requested == ["AlbanAndrieu/foo", "AlbanAndrieu/bar"]


@pytest.mark.parametrize("days", ["0", "-1", "3651", "1000000000"])
def test_days_bounded_without_api_calls(monkeypatch, days):
    monkeypatch.setattr(usage, "items", lambda *args, **kwargs:
                        pytest.fail("unexpected API call"))
    monkeypatch.setattr(sys, "argv", [
        "github-actions-usage.py", "--days", days,
    ])
    with pytest.raises(SystemExit) as error:
        usage.main()
    assert error.value.code == 2


def test_capped_run_history_is_reported_as_partial(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [
        "github-actions-usage.py", "--repo", "one", "--max-runs", "1",
    ])
    calls = []
    monkeypatch.setattr(usage, "recent_runs", lambda *args:
                        calls.append(args) or [{"id": 1, "name": "Build"}])
    monkeypatch.setattr(usage, "items", lambda *args, **kwargs: [])
    monkeypatch.setattr(usage, "job_stats", lambda *args: (1.0, 0))
    assert usage.main() == 1
    stdout, stderr = capsys.readouterr()
    assert len(calls) == 1
    assert "reached --max-runs=1" in stderr
    assert " :: Build\t1\t1.0" in stdout


def test_run_history_below_limit_is_not_flagged_truncated(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [
        "github-actions-usage.py", "--repo", "one", "--max-runs", "2",
    ])
    monkeypatch.setattr(usage, "recent_runs", lambda *args: [
        {"id": 1, "name": "Build"},
    ])
    monkeypatch.setattr(usage, "items", lambda *args, **kwargs: [])
    monkeypatch.setattr(usage, "job_stats", lambda *args: (1.0, 0))
    assert usage.main() == 0
    assert "truncated" not in capsys.readouterr().err
