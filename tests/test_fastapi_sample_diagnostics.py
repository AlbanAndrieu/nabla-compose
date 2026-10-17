"""Offline static/safety contracts for the FastAPI TrueNAS diagnostics."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / "scripts/truenas/diagnose-fastapi-sample.sh"
UPDATE = ROOT / "scripts/truenas/update-fastapi-sample.sh"


def test_shell_syntax() -> None:
    for script in (DIAG, UPDATE):
        result = subprocess.run(
            ["bash", "-n", str(script)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr


def test_diagnostic_help_and_invalid_cycle_budget() -> None:
    ok = subprocess.run(
        ["bash", str(DIAG), "--help"], capture_output=True, text=True, check=False
    )
    assert ok.returncode == 0
    assert "--cycles" in ok.stdout
    bad = subprocess.run(
        ["bash", str(DIAG), "--cycles", "4"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode == 2


def test_diagnostic_never_mutates_runtime_or_shares_credentials() -> None:
    script = DIAG.read_text(encoding="utf-8")
    for forbidden in (
        "docker restart", "docker rm", "docker run", "docker compose up",
        "app.update", "app.redeploy", "app.stop", "docker network create",
        "docker network rm", "--insecure", "printenv", "docker logs",
    ):
        assert forbidden not in script
    assert "--max-time 12" in script
    assert '"$API/api/health-board"' in script
    assert "--no-stream" in script


def test_deployer_summarizes_revision_and_scrubs_auth_smoke_output() -> None:
    script = UPDATE.read_text(encoding="utf-8")
    assert "DEPLOYMENT SUMMARY" in script
    assert "pfsense_report" in script
    assert 'summary passed=[0-9]+ total=[0-9]+ secrets_printed=no' in script
    assert "build_revision=null" in script
    assert "FASTAPI_SAMPLE_REF=<immutable-SHA>" in script
