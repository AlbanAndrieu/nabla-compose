"""Offline syntax gate contracts; no DNS or dependency installation required."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

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


def test_unavailable_diff_falls_back_to_full_syntax_scan(tmp_path: Path) -> None:
    """A failed Git comparison must not produce a false-green empty selection."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "existing.py").write_text("def invalid(:\n", encoding="utf-8")
    subprocess.run(["git", "add", "existing.py"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=CI", "-c", "user.email=ci@example.invalid",
         "commit", "-qm", "fixture"],
        cwd=tmp_path,
        check=True,
    )
    # /tmp can be noexec on TrueNAS. Bash sources BASH_ENV without executing it.
    bash_env = tmp_path / "git-env.sh"
    bash_env.write_text(
        "git() {\n"
        '  if [[ "$1" == diff && "$2" == --name-only && "$3" == --diff-filter=ACMR ]]; then return 99; fi\n'
        '  command git "$@"\n'
        "}\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(GATE)],
        cwd=tmp_path,
        env={**os.environ, "BASH_ENV": str(bash_env), "QUALITY_BASE_REF": "HEAD"},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "offline Git base missing" in result.stderr
    assert "existing.py" in result.stderr


def test_agent_error_excerpt_limits_remain_configurable() -> None:
    gate = (ROOT / "scripts" / "agent-quality-gate.sh").read_text(
        encoding="utf-8"
    )
    assert 'LOG_TAIL="${QUALITY_LOG_TAIL:-32}"' in gate
    assert 'LOG_LINE_MAX="${QUALITY_LOG_LINE_MAX:-320}"' in gate
    assert 'summary_limit="${QUALITY_SUMMARY_LINES:-12}"' in gate
    assert 'awk -v max="${summary_limit}"' in gate
    assert "additional summary lines omitted" in gate
    assert 'print_compact_log "${log}"' in gate
    assert 'return "${rc}"' in gate


def test_offline_inventory_git_failure_is_blocking(tmp_path: Path) -> None:
    """Unavailable Git inventory cannot produce a false-green empty scan."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    bash_env = tmp_path / "git-env.sh"
    bash_env.write_text(
        "git() {\n"
        '  if [[ "$1" == ls-files ]]; then return 97; fi\n'
        '  command git "$@"\n'
        "}\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(GATE)],
        cwd=tmp_path,
        env={
            **os.environ,
            "BASH_ENV": str(bash_env),
            "QUALITY_BASE_REF": "refs/remotes/origin/unavailable",
        },
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "offline file inventory failed" in result.stderr
    assert "syntax + whitespace checks passed" not in result.stdout
