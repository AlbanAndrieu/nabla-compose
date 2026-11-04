"""Offline contract and mocked-command tests for the quick TrueNAS performance mode."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-performance.sh"


def _invoke(tmp_path: Path, *args: str) -> tuple[subprocess.CompletedProcess, list[str]]:
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
        ["bash", str(SCRIPT), *args],
        cwd=ROOT, env=env, capture_output=True,
        text=True, check=False, timeout=18,
    )
    return completed, calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []


def test_quick_skips_expensive_scans_but_preserves_basic_inventory(tmp_path: Path) -> None:
    result, calls = _invoke(tmp_path, "--quick")
    assert result.returncode == 0, result.stderr
    assert "mode=quick" in result.stdout
    assert "SKIPPED (quick mode" in result.stdout
    assert "docker ps -a" in calls
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
    assert not any("SKIPPED (quick mode" in line for line in result.stdout.splitlines())


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
