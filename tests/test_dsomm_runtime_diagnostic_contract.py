"""Contracts for a non-destructive DSOMM UI and import preflight."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/truenas/diagnose-dsomm-assessment.sh"


def test_dsomm_diagnostic_shell_contract() -> None:
    check = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
    assert check.returncode == 0, check.stderr


def test_dsomm_diagnostic_does_not_override_assessments() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "validate-seed.py" in source
    assert "aggregate-repository-assessments.py" in source
    assert "--check" in source
    assert "team-progress.yaml" in source
    assert "team-evidence.yaml" in source
    assert "localStorage" in source
    for forbidden in ("app.redeploy", "app.update", "rm -rf", "docker restart", "--apply"):
        assert forbidden not in source
