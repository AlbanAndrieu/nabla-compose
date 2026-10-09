"""Offline syntax gate contracts; no DNS or dependency installation required."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "agent-offline-check.sh"


def invoke(path: Path, *, limit: str = "0") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(GATE)],
        cwd=path,
        env={
            **os.environ,
            "QUALITY_BASE_REF": "refs/remotes/origin/unavailable",
            "AGENT_OFFLINE_MAX_PATHS": limit,
        },
        capture_output=True,
        text=True,
        check=False,
    )


def test_disconnected_monorepo_checks_more_than_200_files(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for index in range(205):
        (tmp_path / f"module_{index:03d}.py").write_text(
            "value = 1\n", encoding="utf-8"
        )

    result = invoke(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "files=205, parsed=205" in result.stdout
    assert "NOT VERIFIED" in result.stdout


def test_explicit_limit_is_fail_closed(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for index in range(3):
        (tmp_path / f"module_{index}.py").write_text("value = 1\n", encoding="utf-8")

    result = invoke(tmp_path, limit="2")
    assert result.returncode == 2
    assert "offline scope 3 exceeds maximum 2" in result.stderr


def test_invalid_bash_remains_blocking(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "invalid.sh").write_text("if then\n", encoding="utf-8")
    result = invoke(tmp_path)
    assert result.returncode != 0
