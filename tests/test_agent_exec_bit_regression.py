"""Regression for the executable-bit gate: verify behavior, not just syntax."""
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/agent-quality-gate.sh"


def test_executable_gate_rejects_non_executable_shebang(tmp_path):
    text = GATE.read_text(encoding="utf-8")
    start = text.index("check_exec_bits() {")
    end = text.index("\ncheck_base_freshness\n", start)
    function = text[start:end]
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    script = tmp_path / "example.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    subprocess.run(["git", "add", "example.sh"], cwd=tmp_path, check=True)
    invocation = function + '\nMODE=preflight\nCHANGED_FILES=(example.sh)\ncheck_exec_bits\n'
    failed = subprocess.run(["bash", "-e", "-c", invocation], cwd=tmp_path,
                            text=True, capture_output=True)
    assert failed.returncode != 0
    assert "QG_EXEC_BIT" in failed.stderr
    assert "executable-script contract" not in failed.stdout

    subprocess.run(["git", "update-index", "--chmod=+x", "example.sh"],
                   cwd=tmp_path, check=True)
    # Git tracks the executable bit, but does not chmod the checkout itself.
    # The gate intentionally requires owner-executable worktree permissions.
    script.chmod(0o700)
    executable = subprocess.run(
        ["bash", "-c", '[[ -x "$1" ]]', "_", str(script)],
        check=False,
    )
    if executable.returncode != 0:
        # On some TrueNAS ACL/noexec mounts, chmod cannot grant effective
        # execute access. This is a mount-policy limitation, not a Git-index
        # failure; keep the negative security assertion above active.
        pytest.skip("fixture filesystem denies execute access after chmod 0700")
    passed = subprocess.run(["bash", "-e", "-c", invocation], cwd=tmp_path,
                            text=True, capture_output=True)
    assert passed.returncode == 0, passed.stderr
    assert "executable-script contract" in passed.stdout


def test_gate_bash_syntax():
    subprocess.run(["bash", "-n", str(GATE)], check=True)


def test_gate_has_single_completion_block():
    text = GATE.read_text(encoding="utf-8")
    assert text.count("check_exec_bits() {") == 1
    assert [line for line in text.splitlines() if line in ("check_base_freshness", "check_destructive_diff", "check_exec_bits")] == ["check_base_freshness", "check_destructive_diff", "check_exec_bits"]
    assert "read -r tracked_exec path; do" not in text
    assert text.rstrip().endswith("fi")
