"""Offline contract and mocked-command tests for the quick TrueNAS performance mode."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-performance.sh"


def _invoke(
    tmp_path: Path, *args: str, script: Path = SCRIPT
) -> tuple[subprocess.CompletedProcess, list[str]]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "calls.txt"
    commands = ("docker", "midclt", "zpool", "zfs", "vmstat", "journalctl")
    shim = """#!/usr/bin/env bash
printf '%s %s\\n' "${0##*/}" "$*" >> "$TEST_CALLS"
case "${0##*/}" in
  midclt) printf '[]\\n' ;;
  docker)
    if [[ "${1:-}" == ps && "${2:-}" == -a ]]; then
      printf 'NAME STATUS IMAGE\\n'
    elif [[ "${1:-}" == ps && "${2:-}" == --no-trunc ]]; then
      printf '%064d fixture-container\\n' 0
    fi
    ;;
  zpool) printf 'pool status=ONLINE\\n' ;;
  vmstat) printf 'vmstat mock\\n' ;;
esac
"""
    for command in commands:
        path = fake_bin / command
        path.write_text(shim, encoding="utf-8")
        path.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "PATH": f"{fake_bin}:{env['PATH']}",
        "TEST_CALLS": str(calls),
        "NABLA_DIAGNOSTIC_WRAPPED": "1",
        "DIAGNOSTIC_FULL_OUTPUT": "1",
    })
    completed = subprocess.run(
        ["bash", str(script), *args],
        cwd=ROOT, env=env, capture_output=True,
        text=True, check=False, timeout=18,
    )
    return completed, calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []


def test_quick_skips_expensive_scans_but_preserves_basic_inventory(tmp_path: Path) -> None:
    result, calls = _invoke(tmp_path, "--quick")
    assert result.returncode == 0, result.stderr
    assert "mode=quick" in result.stdout
    assert "SKIPPED (quick mode" in result.stdout
    assert any(line.startswith("docker ps -a --format ") for line in calls)
    assert "vmstat 1 1" in calls
    assert not any(line.startswith("docker stats") for line in calls)
    assert not any(line.startswith("docker system df") for line in calls)
    assert not any(line.startswith("docker inspect") for line in calls)
    assert not any(line.startswith("zpool iostat") for line in calls)
    assert not any(line.startswith("zfs list") for line in calls)
    assert any(line.startswith("journalctl -k -b -n 500") for line in calls)
    assert sum(line.startswith("midclt call app.query") for line in calls) <= 1


def test_full_mode_keeps_existing_expensive_diagnostics(tmp_path: Path) -> None:
    result, calls = _invoke(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "mode=full" in result.stdout
    assert "vmstat 1 5" in calls
    assert any(line.startswith("docker stats --no-stream") for line in calls)
    assert "docker system df" in calls
    assert "zpool iostat -v cpool 1 3" in calls
    assert any(line.startswith("zfs list -H -t snapshot") for line in calls)
    assert not any(
        line.startswith("-- expensive Docker checks SKIPPED")
        or line.startswith("-- cpool I/O and snapshot count SKIPPED")
        for line in result.stdout.splitlines()
    )


@pytest.mark.parametrize("args", [("--unknown",), ("--quick", "--full")])
def test_invalid_modes_are_rejected_before_collecting_evidence(
    tmp_path: Path, args: tuple[str, ...],
) -> None:
    result, calls = _invoke(tmp_path, *args)
    assert result.returncode == 2
    assert not calls


def test_syntax_and_explicit_help_do_not_query_runtime() -> None:
    syntax = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False,
    )
    assert syntax.returncode == 0, syntax.stderr
    help_result = subprocess.run(
        ["bash", str(SCRIPT), "--help"], capture_output=True, text=True,
        check=False, env={**os.environ, "NABLA_DIAGNOSTIC_WRAPPED": "1"},
    )
    assert help_result.returncode == 0
    assert "--quick" in help_result.stdout


def test_memory_peaks_is_bounded_and_unavailable_cgroup_is_not_zero(tmp_path: Path) -> None:
    result, calls = _invoke(tmp_path, "--memory-peaks")
    assert result.returncode == 2
    assert "peak_MiB current_MiB limit_bytes name" in result.stdout
    assert "UNVERIFIED UNVERIFIED UNVERIFIED fixture-container" in result.stdout
    assert calls == ["docker ps --no-trunc --format {{.ID}} {{.Names}}"]


def _fixture_cgroup_script(tmp_path: Path, root: Path) -> Path:
    script = tmp_path / "scripts" / "truenas" / SCRIPT.name
    script.parent.mkdir(parents=True)
    script.write_text(SCRIPT.read_text(encoding="utf-8").replace("/sys/fs/cgroup", str(root)), encoding="utf-8")
    lib = script.parent.parent / "lib"
    lib.mkdir()
    shutil.copyfile(ROOT / "scripts/lib/diagnostic.sh", lib / "diagnostic.sh")
    return script


def test_memory_peaks_reads_and_rounds_cgroup_charges(tmp_path: Path) -> None:
    # Substitute only the cgroup root in the fixture, never on TrueNAS.
    root = tmp_path / "cgroup"
    group = root / "system.slice" / ("docker-" + "0" * 64 + ".scope")
    group.mkdir(parents=True)
    (group / "memory.peak").write_text(str(1024 * 2**20 + 1), encoding="utf-8")
    (group / "memory.current").write_text(str(512 * 2**20 + 1), encoding="utf-8")
    (group / "memory.max").write_text("max", encoding="utf-8")
    script = _fixture_cgroup_script(tmp_path, root)
    result, calls = _invoke(tmp_path, "--memory-peaks", script=script)
    assert result.returncode == 0, result.stderr
    assert "1025 513 max fixture-container" in result.stdout
    assert calls == ["docker ps --no-trunc --format {{.ID}} {{.Names}}"]



@pytest.mark.parametrize("layout", ["docker", "systemd"])
def test_memory_events_reports_cumulative_counts_with_one_inventory(
    tmp_path: Path, layout: str,
) -> None:
    root = tmp_path / "cgroup"
    if layout == "docker":
        group = root / "docker" / ("0" * 64)
    else:
        group = root / "system.slice" / ("docker-" + "0" * 64 + ".scope")
    group.mkdir(parents=True)
    (group / "memory.events").write_text(
        "low 0\nhigh 7\nmax 123\noom 2\noom_kill 1\noom_group_kill 0\n",
        encoding="utf-8",
    )
    result, calls = _invoke(tmp_path, "--memory-events", script=_fixture_cgroup_script(tmp_path, root))
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["high max oom oom_kill name", "7 123 2 1 fixture-container"]
    assert calls == ["docker ps --no-trunc --format {{.ID}} {{.Names}}"]


@pytest.mark.parametrize("events", [
    None,
    "high 0\nmax 0\noom 0\n",
    "high 0\nmax invalid\noom 0\noom_kill 0\n",
    "high 0\nmax 0\nmax 1\noom 0\noom_kill 0\n",
])
def test_memory_events_unavailable_is_not_zero(tmp_path: Path, events: str | None) -> None:
    root = tmp_path / "cgroup"
    group = root / "docker" / ("0" * 64)
    group.mkdir(parents=True)
    if events is not None:
        (group / "memory.events").write_text(events, encoding="utf-8")
    result, calls = _invoke(tmp_path, "--memory-events", script=_fixture_cgroup_script(tmp_path, root))
    assert result.returncode == 2
    assert "UNVERIFIED UNVERIFIED UNVERIFIED UNVERIFIED fixture-container" in result.stdout
    assert calls == ["docker ps --no-trunc --format {{.ID}} {{.Names}}"]
