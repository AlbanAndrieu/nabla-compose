"""Offline agent context regression tests (no network or external services)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

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


def test_context_handles_existing_but_unrelated_base(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    identity = ["git", "-c", "user.name=CI", "-c", "user.email=ci@example.invalid"]
    (tmp_path / "first.txt").write_text("first\n", encoding="utf-8")
    subprocess.run(["git", "add", "first.txt"], cwd=tmp_path, check=True)
    subprocess.run([*identity, "commit", "-qm", "base"], cwd=tmp_path, check=True)
    old_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True,
        capture_output=True, check=True,
    ).stdout.strip()
    subprocess.run(["git", "checkout", "-q", "--orphan", "disconnected"],
                   cwd=tmp_path, check=True)
    subprocess.run(["git", "rm", "-q", "-rf", "."], cwd=tmp_path, check=True)
    (tmp_path / "second.txt").write_text("second\n", encoding="utf-8")
    subprocess.run(["git", "add", "second.txt"], cwd=tmp_path, check=True)
    subprocess.run([*identity, "commit", "-qm", "unrelated"],
                   cwd=tmp_path, check=True)
    (tmp_path / "untracked.txt").write_text("new\n", encoding="utf-8")

    result = subprocess.run(
        ["python3", str(CONTEXT_SCRIPT)],
        cwd=tmp_path,
        env={**os.environ, "QUALITY_BASE_REF": old_sha},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "changed-paths: 1" in result.stdout
    assert "untracked.txt" in result.stdout
