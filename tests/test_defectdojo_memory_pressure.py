"""TrueNAS ZFS ARC and DefectDojo pressure diagnostics: fixture-only tests."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/truenas/diagnose-defectdojo-memory-pressure.py"
SPEC = importlib.util.spec_from_file_location("defectdojo_memory_pressure", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_memavailable_is_not_memfree(tmp_path):
    file = tmp_path / "meminfo"
    file.write_text(
        "MemTotal: 16777216 kB\n"
        "MemAvailable: 6291456 kB\n"
        "MemFree: 65536 kB\n"
        "Cached: 4096000 kB\n"
        "SwapTotal: 1048576 kB\n"
        "SwapFree: 786432 kB\n"
    )
    sample = MODULE.read_memory_info(file)
    assert sample["MemAvailable"] == 6 * 1024**3
    assert sample["MemFree"] == 64 * 1024**2
    assert sample["MemAvailable"] > sample["MemFree"]


def test_psi_percentages(tmp_path):
    file = tmp_path / "pressure"
    file.write_text("some avg10=12.50 avg60=4.00 total=10\n"
                    "full avg10=2.50 avg60=0.25 total=1\n")
    result = MODULE.read_pressure(file)
    assert result == {"some_avg10_pct": 12.5, "full_avg10_pct": 2.5}


def test_zfs_arc_potential_reclaim_not_absolute_memory(tmp_path):
    file = tmp_path / "arcstats"
    file.write_text("13 1 0x01 123 567\n"
                    "name type data\n"
                    "size 4 8589934592\n"
                    "c_min 4 2147483648\n"
                    "c 4 4294967296\n")
    result = MODULE.read_arc(file)
    assert result["size_bytes"] == 8 * 1024**3
    assert result["potential_shrink_bytes"] == 6 * 1024**3


def test_cgroup_events_are_cumulative(tmp_path):
    file = tmp_path / "events"
    file.write_text("low 0\nhigh 123\nmax 2\noom 1\noom_kill 1\n")
    result = MODULE.read_memory_events(file)
    assert result["oom_kill"] == 1
    assert "low" not in result


def test_rss_normalization():
    assert MODULE.parse_size("1.25GiB") == int(1.25 * 1024**3)
    assert MODULE.parse_size("640 MiB") == 640 * 1024**2
    assert MODULE.parse_size("???") is None


def test_docker_stats_only_exposes_names_and_memory(monkeypatch):
    stdout = "\n".join(json.dumps(row) for row in (
        {"Name": "defectdojo-uwsgi", "MemUsage": "1.5GiB / 16GiB",
         "Env": "DD_SECRET_KEY=LEAK", "CPUPerc": "95%"},
        {"Name": "defectdojo-celeryworker", "MemUsage": "512MiB / 16GiB"},
        {"Name": "postgres", "MemUsage": "2GiB / 16GiB"},
    ))
    monkeypatch.setattr(MODULE.subprocess, "run",
                        lambda *_a, **_kw: SimpleNamespace(returncode=0, stdout=stdout))
    result = MODULE.docker_snapshot()
    assert result["status"] == "OBSERVED"
    assert result["defectdojo_total_bytes"] == 2 * 1024**3
    assert len(result["top_memory_containers"]) == 3
    assert "DD_SECRET_KEY" not in json.dumps(result)
    assert "LEAK" not in json.dumps(result)


def test_docker_failure_does_not_emit_stderr(monkeypatch):
    monkeypatch.setattr(MODULE.subprocess, "run",
                        lambda *_a, **_kw: SimpleNamespace(
                            returncode=1, stdout="", stderr="SECRET_FAILURE"))
    assert MODULE.docker_snapshot()["status"] == "UNVERIFIED"


@pytest.mark.parametrize(("available", "psi_some", "psi_full", "expected"), [
    (0.03, 18.0, 2.0, "PRESSURE_LIKELY"),
    (0.30, 0.0, 0.0, "NO_CURRENT_PRESSURE_SIGNAL"),
    (0.08, 0.5, 0.0, "INCONCLUSIVE"),
])
def test_pressure_requires_more_than_free_memory(available, psi_some, psi_full, expected):
    memory = {"MemTotal": 1000000, "MemAvailable": int(available * 1000000)}
    psi = {"some_avg10_pct": psi_some, "full_avg10_pct": psi_full}
    assert MODULE.assess(memory, psi, {}) == expected
