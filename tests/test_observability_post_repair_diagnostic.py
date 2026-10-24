"""Offline contract for bounded, read-only observability triage."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/truenas/diagnose-observability-post-repair.sh'


def _run_with_mock_commands(tmp_path: Path, *, healthy: bool) -> subprocess.CompletedProcess[str]:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1\" == inspect ]]; then\n"
        "  if [[ \"$*\" == *prometheus* ]]; then\n"
        "    echo 'restarting|2|false|12'; else echo 'running|0|false|1'; fi\n"
        "elif [[ \"$1\" == logs ]]; then\n"
        "  if [[ \"$*\" == *prometheus* ]]; then\n"
        "    echo 'secret=DO_NOT_PRINT rules permission denied'; else\n"
        "    echo 'secret=DO_NOT_PRINT non-monotonic log entries'; fi\n"
        "else exit 2; fi\n"
    )
    docker.chmod(0o755)
    curl = binaries / "curl"
    curl.write_text(
        "#!/usr/bin/env bash\n"
        + ("printf '200'\n" if healthy else "printf '000'\nexit 7\n")
    )
    curl.chmod(0o755)
    env = dict(os.environ, PATH=f"{binaries}:{os.environ['PATH']}")
    return subprocess.run(
        ["bash", str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=10,
    )


@pytest.mark.parametrize("healthy", [False, True])
def test_triage_only_emits_allowlisted_metadata(tmp_path: Path, healthy: bool) -> None:
    result = _run_with_mock_commands(tmp_path, healthy=healthy)
    assert result.returncode == (0 if healthy else 1), result.stderr
    assert "rule_read_permission" in result.stdout
    assert "raft_non_monotonic" in result.stdout
    assert "DO_NOT_PRINT" not in result.stdout + result.stderr
    assert "exit=2" in result.stdout
    assert "oom=false" in result.stdout


def test_apply_not_supported(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "--apply"],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 2


def test_no_mutation_or_raw_log_output() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "docker restart", "docker stop", "docker start", "docker exec",
        "chmod ", "chown ", "rm -rf", "docker compose", "zfs destroy",
        "printf '%s' \"${logs}\"", "--apply",
    ):
        assert forbidden not in source
    bash_syntax = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bash_syntax.returncode == 0, bash_syntax.stderr
