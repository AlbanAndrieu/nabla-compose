"""Offline shell/skill contracts for the workstation vs remote diagnostic router."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/agent-diagnostics.sh"


def invoke(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=ROOT,
                          env={**os.environ, **(env or {})},
                          text=True, capture_output=True, check=False, timeout=10)


def test_shell_syntax_and_help() -> None:
    assert subprocess.run(["bash", "-n", str(SCRIPT)], check=False).returncode == 0
    result = invoke("--help")
    assert result.returncode == 0
    assert "offline|workstation" in result.stdout


def test_offline_mode_never_attempts_private_runtime() -> None:
    result = invoke("--runtime", "prometheus", env={"AGENT_EXECUTION_MODE": "offline"})
    assert result.returncode == 2
    assert "NOT_RUN" in result.stderr


def test_invalid_workstation_service_is_rejected_before_network() -> None:
    result = invoke("--mode", "workstation", "--runtime", "../secrets")
    assert result.returncode == 2
    assert "invalid service ID" in result.stderr


def test_unbounded_workstation_fanout_is_rejected() -> None:
    result = invoke("--mode", "workstation", "--runtime", "a", "b", "c", "d")
    assert result.returncode == 2
    assert "1..3" in result.stderr


def test_skills_are_progressively_loaded() -> None:
    for name, reference in (
        ("homelab-runtime-status", "references/runtime-inspection.md"),
        ("homelab-secrets", "references/secrets-migration.md"),
    ):
        skill = ROOT / ".agents/skills" / name / "SKILL.md"
        raw = skill.read_text(encoding="utf-8")
        assert reference in raw
        assert (skill.parent / reference).is_file()
        assert len(raw.splitlines()) < 55


def test_agent_policy_keeps_modes_and_security() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "AGENT_EXECUTION_MODE=workstation" in text
    assert "AGENT_EXECUTION_MODE=offline" in text
    assert "Do not run" in text
    assert "Ask the user before installing" in text
    assert len(text.splitlines()) < 110
