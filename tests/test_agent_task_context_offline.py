"""Offline agent context regression tests (no network or external services)."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CONTEXT_SCRIPT = ROOT / "scripts" / "agent-task-context.py"


def test_context_is_bounded_without_remote_git_base(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for index in range(30):
        (tmp_path / f"changed-{index:02d}.txt").write_text("test\n", encoding="utf-8")

    env = {
        **os.environ,
        "QUALITY_BASE_REF": "refs/remotes/origin/unavailable",
        "AGENT_CONTEXT_MAX_PATHS": "3",
    }
    result = subprocess.run(
        ["python3", str(CONTEXT_SCRIPT)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "changed-paths: 30" in result.stdout
    assert "27 more; use git diff --name-only" in result.stdout
    assert "27 more; use git status --short" in result.stdout
    assert result.stdout.count("  - changed-") == 3


def test_context_rejects_invalid_output_bound(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    result = subprocess.run(
        ["python3", str(CONTEXT_SCRIPT)],
        cwd=tmp_path,
        env={**os.environ, "AGENT_CONTEXT_MAX_PATHS": "0"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "AGENT_CONTEXT_MAX_PATHS must be positive" in result.stderr
