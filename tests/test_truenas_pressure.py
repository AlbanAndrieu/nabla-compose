"""Hermetic TrueNAS host-service pressure diagnostic tests."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "scripts/truenas/diagnose-truenas-pressure.py"
spec = importlib.util.spec_from_file_location("pressure_diag", SOURCE)
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def sample(available=20, mem_full=0, mem_some=0, io_some=0, cpu_some=0):
    return {"memory_available_pct": available, "psi": {
        "memory": {"some_avg10_pct": mem_some, "full_avg10_pct": mem_full},
        "io": {"some_avg10_pct": io_some},
        "cpu": {"some_avg10_pct": cpu_some}}}


def test_meminfo_available_not_memfree():
    data = m.parse_meminfo("MemTotal: 1000 kB\nMemAvailable: 100 kB\nSwapTotal: 10 kB\nSwapFree: 5 kB\nMemFree: 0 kB\n")
    assert data["MemAvailable"] == 100 * 1024


def test_meminfo_missing_refused():
    import pytest
    with pytest.raises(ValueError):
        m.parse_meminfo("MemFree: 8000 kB\n")


def test_psi_nonfinite_rejected():
    assert m.parse_psi("some avg10=NaN avg60=0 avg300=0 total=0\nfull avg10=1.1 avg60=0 avg300=0 total=0") == {"full_avg10_pct": 1.1}


def test_zfs_arc_reports_estimated_shrink_not_unrecoverable():
    assert m.parse_arc("size 4 7000\nc_min 4 2000\nc 4 8000\n")["potential_shrink_bytes"] == 5000


def test_vmstat_deltas_and_reset_are_not_zero():
    before = m.parse_vmstat("oom_kill 5\npswpout 6\npgscan_direct 40\nallocstall_normal 3\n")
    after = m.parse_vmstat("oom_kill 7\npswpout 2\npgscan_direct 42\nallocstall_normal 3\n")
    diff = m.counter_deltas(before, after)
    assert diff["oom_kill"] == 2
    assert diff["pswpout"] == "UNVERIFIED"
    assert diff["direct_reclaim"] == 2


def test_oom_observed_is_critical():
    assert m.assess(sample(), {"oom_kill": 1})[0] == "CRITICAL_PRESSURE"


def test_low_free_memory_alone_is_not_oom():
    state, signals = m.assess(sample(available=4), {"oom_kill": 0})
    assert state == "PRESSURE_SIGNAL"
    assert "new_host_oom_kill" not in signals


def test_memory_psi_full_and_low_available_is_critical():
    assert m.assess(sample(available=3, mem_full=3), {})[0] == "CRITICAL_PRESSURE"


def test_io_pressure_separate_from_memory_pressure():
    state, signals = m.assess(sample(available=40, io_some=22), {})
    assert state == "PRESSURE_SIGNAL"
    assert signals == ["io_stalls"]


def test_docker_stats_names_and_limits_are_redacted_and_sorted():
    raw = "\n".join([
        json.dumps({"Name": "ix-netdata-1", "CPUPerc": "100.0%", "MemUsage": "900MiB / 2GiB", "MemPerc": "45%"}),
        json.dumps({"Name": "ix-opensearch-1", "CPUPerc": "20.0%", "MemUsage": "1.2GiB / 3GiB", "MemPerc": "40%"}),
        json.dumps({"Name": "bad name secret=hi", "CPUPerc": "99%", "MemUsage": "2GiB / 3GiB", "MemPerc": "40%"}),
        json.dumps({"Name": "invalid", "CPUPerc": "NaN%", "MemUsage": "2GiB / 3GiB", "MemPerc": "40%"})
    ])
    report = m.parse_docker_stats(raw, 2)
    assert report["containers_sampled"] == 2
    assert report["top_memory"][0]["name"] == "ix-opensearch-1"
    assert report["top_cpu"][0]["name"] == "ix-netdata-1"
    assert "secret=hi" not in str(report)


def test_docker_timeout_is_unverified():
    with mock.patch.object(m.subprocess, "run", side_effect=subprocess.TimeoutExpired("docker", 2)):
        assert m.docker_sample(2, 5)["state"] == "UNVERIFIED"


def test_private_report_permissions_and_symlink_guard():
    import pytest
    with tempfile.TemporaryDirectory() as dirname:
        root = Path(dirname)
        out = root / "evidence"
        path = m.save_report(out, {"status": "UNVERIFIED"})
        assert path.stat().st_mode & 0o777 == 0o600
        assert out.stat().st_mode & 0o777 == 0o700
        alias = root / "alias"
        alias.symlink_to(out, target_is_directory=True)
        with pytest.raises(ValueError):
            m.save_report(alias / "child", {})


def test_docker_collection_uses_bounded_stats_not_inspect():
    response = subprocess.CompletedProcess([], 0, json.dumps({"Name":"app","CPUPerc":"2%","MemUsage":"100MiB / 1GiB","MemPerc":"10%"})+"\n", "")
    with mock.patch.object(m.subprocess, "run", return_value=response) as proc:
        assert m.docker_sample(8, 10)["state"] == "OBSERVED"
    cmd = proc.call_args.args[0]
    assert cmd[:3] == ["docker", "stats", "--no-stream"]
    assert proc.call_args.kwargs["timeout"] == 8


def test_resource_candidates_are_hints_not_root_cause():
    raw = json.dumps({"Name": "ix-heavy-1", "CPUPerc": "125%",
                      "MemUsage": "2GiB / 3GiB", "MemPerc": "90%"}) + "\n"
    result = m.parse_docker_stats(raw, 10)
    assert result["resource_candidates"] == [
        {"name": "ix-heavy-1", "clues": [
            "high_cpu_snapshot",
            "near_container_memory_limit",
            "large_working_set_not_host_pressure_proof",
        ]}
    ]


def test_host_only_mode_never_queries_docker(capsys):
    fake = {"at_utc": "2026-10-26T22:00:00+00:00",
            "memory_available_pct": 45,
            "memory_available_mib": 4000,
            "memory_total_mib": 8000, "swap_used_mib": 0,
            "psi": {"cpu": {"some_avg10_pct": 0},
                    "memory": {"some_avg10_pct": 0, "full_avg10_pct": 0},
                    "io": {"some_avg10_pct": 0}},
            "vmstat": {"oom_kill": 0}, "zfs_arc": {"state": "UNAVAILABLE"}}
    with (mock.patch.object(m, "host_sample", return_value=fake),
          mock.patch.object(m, "docker_sample") as docker):
        rc = m.main(["--check", "--observe-seconds", "0", "--skip-docker"])
    assert rc == 0
    assert '"SKIPPED"' in capsys.readouterr().out
    docker.assert_not_called()
