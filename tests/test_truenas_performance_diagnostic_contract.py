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


def test_zombie_parents_are_attributed_to_containers_with_one_docker_call() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.count("docker ps --no-trunc --format '{{.ID}} {{.Names}}'") == 1
    assert '"/proc/${ppid}/cgroup"' in source
    assert "[0-9a-f]{64}" in source
    assert "parent zombie container" in source
    # Host-level parents stay visible instead of being dropped.
    assert '"${container:-host}"' in source


def test_stuck_container_locks_are_detected_with_bounded_probes() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    # A hung inspect blocked TrueNAS app.query on 2026-11-04: every probe is bounded.
    assert "xargs -r timeout 60 docker inspect" in source
    assert "timeout 5 docker inspect --format '{{.Name}}'" in source
    assert "$2 ~ /^Z/ && $3 > 1" in source
    assert "zombies with live threads" in source


def test_memory_limits_are_sized_from_cgroup_peaks() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"${dir}/memory.peak"' in source
    assert '"/sys/fs/cgroup/docker/${id}"' in source
    assert '"/sys/fs/cgroup/system.slice/docker-${id}.scope"' in source


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
