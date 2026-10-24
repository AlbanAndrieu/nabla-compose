"""Offline Sentry consumer health diagnostics; no middleware or Kafka access."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-sentry-consumers.sh"


@pytest.mark.parametrize("state,expected_exit,expected_text", [
    ("running|healthy|0|0", 0, "OK: both critical Sentry consumers"),
    ("running|unhealthy|0|2", 1, "unhealthy_or_missing_consumers=2"),
    ("restarting|none|2|20", 1, "unhealthy_or_missing_consumers=2"),
])
def test_sentry_diagnostic_classifies_both_consumers_and_redacts_logs(
    tmp_path, noexec_safe_bash_mocks, state, expected_exit, expected_text
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(chr(10).join((
        "#!/usr/bin/env bash",
        'if [[ "$1" == ps ]]; then',
        '  if [[ "$*" == *"sentry-events-consumer"* ]]; then echo aaaaaaaaaaaa;',
        '  elif [[ "$*" == *"sentry-post-process-forwarder-errors"* ]]; then',
        '    echo bbbbbbbbbbbb;',
        '  fi',
        'elif [[ "$1" == inspect ]]; then',
        '  if [[ "$*" == *"FailingStreak"* ]]; then',
        '    echo "3|1 1 2 "',
        '  else echo "$MOCK_SENTRY_STATE"; fi',
        'elif [[ "$1" == logs ]]; then',
        "  echo 'SESSTMOUT kafka coordinator rebalance PRIVATE-TOKEN-NEVER-SHOW'",
        'else exit 99; fi',
        "",
    )), encoding="utf-8")
    docker.chmod(0o600)
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
    env["MOCK_SENTRY_STATE"] = state
    env = noexec_safe_bash_mocks(env, "docker")
    result = subprocess.run(
        ["bash", str(SCRIPT), "--check"],
        capture_output=True, text=True, env=env, check=False, timeout=15
    )
    output = result.stdout + result.stderr
    assert result.returncode == expected_exit, output
    assert expected_text in output
    assert "PRIVATE-TOKEN" not in output
    if expected_exit:
        assert "kafka_coordination=1" in output
        assert "healthcheck_failing_streak=3 last_probe_exit=2" in output
        assert "evidence=empty_recent_logs_do_not_prove_kafka_timeout" in output


def test_sentry_diagnostic_is_read_only_and_bash_valid():
    proc = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True,
                          text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    contents = SCRIPT.read_text(encoding="utf-8")
    assert "com.docker.compose.project=" in contents
    assert "sentry-events-consumer" in contents
    assert "sentry-post-process-forwarder-errors" in contents
    for forbidden in (
        "docker restart", "docker exec", "docker start",
        "app.redeploy", "app.update", "rm -rf", ".Config.Env",
        "kafka-consumer-groups --reset-offsets",
    ):
        assert forbidden not in contents
