"""Contracts for the bounded TrueNAS Gatus reconciliation path."""

from pathlib import Path
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "scripts/truenas/deploy-gatus.sh"


def test_gatus_deployer_parses_and_is_executable() -> None:
    result = subprocess.run(
        ["bash", "-n", str(DEPLOY)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert DEPLOY.stat().st_mode & stat.S_IXUSR


def test_gatus_deployer_reconciles_compose_and_preserves_sqlite() -> None:
    source = DEPLOY.read_text(encoding="utf-8")

    for expected in (
        "truenas_reconcile_custom_app",
        "truenas_wait_app_running",
        "repair-gatus-config-access.sh",
        "diagnose-gatus.sh",
        "/mnt/cpool/gatus/gatus.db",
        "stat -c '%d:%i'",
        "existing Gatus SQLite inode preserved",
        "http://172.17.0.24:8085/health",
    ):
        assert expected in source

    for forbidden in (
        "rm -f",
        "rm -rf",
        "sqlite3",
        "chmod -R",
        "chown -R",
        "docker rm",
        "docker volume rm",
        "docker system prune",
    ):
        assert forbidden not in source
