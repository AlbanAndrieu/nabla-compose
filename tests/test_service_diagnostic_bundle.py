"""Offline contracts for the bounded service diagnostics coordinator."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts/truenas/diagnose-service-bundle.py"
)
SPEC = importlib.util.spec_from_file_location("diagnose_service_bundle", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
import sys
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_plan_is_not_a_runtime_probe() -> None:
    result = subprocess.run(
        ["python3", str(SCRIPT), "--plan", "--section", "observability"],
        capture_output=True,
        check=False,
        text=True,
        timeout=6,
    )
    assert result.returncode == 0
    assert '"mode": "plan"' in result.stdout
    assert '"mutations": false' in result.stdout


def test_fixed_allowlist_no_shell_and_no_raw_output() -> None:
    seen: list[tuple[str, ...]] = []

    def fake_runner(args, **kwargs):
        seen.append(tuple(args))
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["stdout"] is subprocess.DEVNULL
        assert kwargs["stderr"] is subprocess.DEVNULL
        assert kwargs["check"] is False
        assert kwargs["timeout"] <= 45
        assert "shell" not in kwargs
        return SimpleNamespace(returncode=0)

    checks = MODULE.selected_checks("observability")
    results = MODULE.collect(checks, runner=fake_runner)
    assert MODULE.overall_exit(results) == 0
    assert len(seen) == 3
    assert set(x["state"] for x in results) == {"pass"}
    for command in seen:
        assert command[0] in {"python3", "bash"}
        assert command[1].startswith("scripts/")
        assert not any("sudo" in value or "--apply" in value for value in command)


def test_failure_isolation_and_no_false_green() -> None:
    count = 0

    def fake_runner(_args, **_kwargs):
        nonlocal count
        count += 1
        return SimpleNamespace(returncode=[1, 2, 0][count - 1])

    results = MODULE.collect(
        MODULE.selected_checks("observability"), runner=fake_runner
    )
    assert count == 3
    assert [x["state"] for x in results] == [
        "failed", "unverified", "pass",
    ]
    assert MODULE.overall_exit(results) == 1


def test_timeout_and_missing_tools_never_pass() -> None:
    def timeout(_args, **_kwargs):
        raise subprocess.TimeoutExpired("private", 5)

    results = MODULE.collect(
        (MODULE.selected_checks("observability")[0],), runner=timeout
    )
    assert results[0]["state"] == "timeout"
    assert MODULE.overall_exit(results) == 1
    assert MODULE.overall_exit([{"state": "unverified"}]) == 2


@pytest.mark.parametrize("mode", ["--apply", "--restart", "--deploy"])
def test_mutating_args_rejected(mode: str) -> None:
    result = subprocess.run(
        ["python3", str(SCRIPT), mode],
        capture_output=True,
        text=True,
        check=False,
        timeout=6,
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_allowlist_has_no_dynamic_endpoints_or_logs() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for unsafe in (
        "docker restart", "docker exec", "docker stop", "rm -rf",
        "sudo ", "os.system(", "shell=True", "print(finished.stdout)",
        "print(finished.stderr)", "http://", "https://",
    ):
        assert unsafe not in source
    assert "subprocess.DEVNULL" in source
    assert 'choices=SECTIONS' in source
