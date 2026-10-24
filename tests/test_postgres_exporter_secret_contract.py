"""Safe declarative contract for the optional TrueNAS PostgreSQL exporter."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "apps/postgres/compose.yml"
DIAG = ROOT / "scripts/truenas/diagnose-postgres-exporter.sh"
INSTALLER = ROOT / "scripts/truenas/install-runtime-secret.sh"
EXPECTED_SECRET = "/mnt/cpool/secrets/runtime/postgres-exporter/.env.secrets"


def test_exporter_uses_dedicated_materialized_secret_without_interpolation() -> None:
    config = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    service = config["services"]["postgres_exporter"]
    assert service["env_file"] == [{
        "path": EXPECTED_SECRET,
        "required": True,
        "format": "raw",
    }]
    assert "environment" not in service
    assert "POSTGRES_EXPORTER_DSN" not in COMPOSE.read_text(encoding="utf-8")
    assert service["ports"][0]["host_ip"] == "172.17.0.24"
    assert service["ports"][0]["published"] == "9187"


def test_exporter_is_independent_from_db_and_not_published_to_wan() -> None:
    config = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    service = config["services"]["postgres_exporter"]
    assert list(config["services"]) == ["postgres_exporter"]
    assert service["ports"][0]["target"] == 9187
    assert service["restart"] == "unless-stopped"


def test_diagnostic_never_reads_privileged_postgres_application_secrets() -> None:
    source = DIAG.read_text(encoding="utf-8")
    assert EXPECTED_SECRET in source
    assert 'DATA_SOURCE_NAME=' in source
    assert "root:root mode 600" in source
    assert "/mnt/cpool/postgres/.env.secrets" not in source
    assert "echo \"${POSTGRES_EXPORTER_DSN}\"" not in source
    result = subprocess.run(
        ["bash", "-n", str(DIAG)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_secret_installation_does_not_expose_exporter_dsn() -> None:
    source = INSTALLER.read_text(encoding="utf-8")
    assert "DEST_DIR=" in source
    assert "SOURCE" in source
    assert "root:root 600" in source
    assert "cmp -s" in source
