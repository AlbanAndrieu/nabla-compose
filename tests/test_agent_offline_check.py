"""Regression contracts for offline, dependency-free agent checks."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "agent-offline-check.sh"


def run_gate(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(GATE)],
        cwd=tmp_path,
        env={**os.environ, "QUALITY_BASE_REF": "refs/remotes/origin/unavailable"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_offline_gate_works_without_remote_or_hooks(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "ok.sh").write_text("printf '%s\\n' ok\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    result = run_gate(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "parsed=2" in result.stdout
    assert "NOT VERIFIED" in result.stdout


def test_offline_gate_fails_on_invalid_shell_syntax(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "broken.sh").write_text("if then\n", encoding="utf-8")
    result = run_gate(tmp_path)
    assert result.returncode != 0


def test_offline_gate_fails_on_invalid_python_syntax(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    result = run_gate(tmp_path)
    assert result.returncode != 0
