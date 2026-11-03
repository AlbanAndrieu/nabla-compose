"""Offline, non-mutating contracts for the TrueNAS performance diagnostic."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-performance.sh"


def test_true_nas_inventory_is_fetched_once_and_two_views_are_retained() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.count("midclt call app.query") == 1
    assert 'section "TrueNAS app states"' in source
    assert "-- non-running apps --" in source
    assert "sort -k2,2 -k1,1" in source
    assert '$2 != "RUNNING"' in source
    # Only the sanitized app ID, state and count are retained for the views.
    assert "((.active_workloads.containers // 0) | tostring)" in source
    assert "app_rows=" in source


def test_containerd_pid_is_looked_up_only_once() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.count("pgrep -o -x containerd") == 1
    assert source.count("containerd_pid") >= 3
    assert "process not found" in source


def test_shell_syntax_is_valid_without_running_true_nas_diagnostics() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def test_expensive_checks_remain_bounded_and_read_only() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "timeout 60 docker system df" in source
    assert "docker stats --no-stream" in source
    assert "midclt call app.query" in source
    assert "nabla_diagnostic_maybe_wrap" in source
    for unsafe in ("docker prune", "docker restart", "midclt call app.update",
                   "docker volume rm", "zfs destroy"):
        assert unsafe not in source
