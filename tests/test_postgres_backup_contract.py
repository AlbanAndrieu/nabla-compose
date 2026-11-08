"""Contracts for the versioned PostgreSQL logical backup job (owner decision 2026-11-07)."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "apps" / "postgres-backup" / "compose.yml"
SCRIPT = ROOT / "apps" / "postgres-backup" / "backup.sh"
CRON = ROOT / "scripts" / "truenas" / "reconcile-postgres-backup-cron.py"
ROLE = ROOT / "scripts" / "truenas" / "bootstrap-postgres-backup-role.sh"
# Shared TrueNAS PostgreSQL server image observed on 2026-11-06 (app `postgres`).
SERVER_IMAGE = "postgres:18.6-trixie@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6"


def _service() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["postgres-backup"]


def test_job_uses_the_server_image_digest_and_never_starts_a_server() -> None:
    service = _service()

    assert service["image"] == SERVER_IMAGE
    assert service["entrypoint"] == ["bash", "/opt/nabla/backup.sh"]
    assert service["restart"] == "no"
    assert service["profiles"] == ["manual"]


def test_job_is_hardened_and_uses_canonical_runtime_secret() -> None:
    service = _service()

    assert service["env_file"] == ["/mnt/cpool/secrets/runtime/postgres-backup/.env.secrets"]
    assert service["read_only"] is True
    assert "ALL" in service["cap_drop"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert service["user"] == "568:568"
    assert "/mnt/cpool/backup/postgres:/backups" in service["volumes"]
    assert service["environment"]["POSTGRES_USER"] == "pgbackup"
    assert "POSTGRES_PASSWORD" not in service["environment"]


def test_backup_script_verifies_prunes_and_keeps_the_password_off_argv() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert script.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in script
    assert "--format=custom" in script and "pg_restore --list" in script
    assert 'export PGPASSWORD="${POSTGRES_PASSWORD}"' in script and "unset POSTGRES_PASSWORD" in script
    assert "--password" not in script and "PGPASSWORD=" not in script.replace('export PGPASSWORD="${POSTGRES_PASSWORD}"', "")
    assert "-mtime +\"${KEEP_DAYS}\"" in script
    assert ".last-success.json" in script
    assert re.search(r"\[\[ \"\$\{database\}\" =~ \^\[a-z\]", script)


def test_all_missing_databases_never_mark_backup_success(tmp_path: Path) -> None:
    # The fake server is reachable but has no database yet: common during rollout.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_psql = fake_bin / "psql"
    fake_psql.write_text("#!/bin/sh\\nprintf '0\\\\n'\\n", encoding="utf-8")
    fake_psql.chmod(0o755)
    existing = tmp_path / ".last-success.json"
    existing.write_text('{"completed_at":"previous-validated-backup"}\\n', encoding="utf-8")
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_USER": "pgbackup",
        "POSTGRES_PASSWORD": f"test-fixture-{os.getpid()}",
        "BACKUP_DATABASES": "not_created_a not_created_b",
        "BACKUP_DIR": str(tmp_path),
        "BACKUP_REQUIRE_ALL": "false",
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True,
        text=True, check=False, timeout=10,
    )
    assert result.returncode == 1, result.stderr
    assert "FAIL no database backup completed" in result.stderr
    assert existing.read_text(encoding="utf-8") == (
        '{"completed_at":"previous-validated-backup"}\\n'
    )
    assert not list(tmp_path.rglob("*.dump"))


def test_cron_reconciler_registers_disabled_and_gates_enable() -> None:
    spec = importlib.util.spec_from_file_location("reconcile_postgres_backup_cron", CRON)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.JOB["enabled"] is False
    assert module.JOB["user"] == "root"
    assert "--profile manual run --rm --no-deps postgres-backup" in module.JOB["command"]
    assert "/mnt/cpool/compose/nabla-compose/apps/postgres-backup" in module.JOB["command"]
    source = CRON.read_text(encoding="utf-8")
    assert "POSTGRES_BACKUP_CRON_APPROVED" in source
    assert "refuse mutation" in source


def test_role_bootstrap_is_read_only_and_matches_the_job() -> None:
    script = ROLE.read_text(encoding="utf-8")

    assert 'MODE="${1:---check}"' in script
    assert "/mnt/cpool/secrets/runtime/postgres-backup/.env.secrets" in script
    assert ":-pgbackup}" in script
    assert "LOGIN NOREPLICATION" in script and "pg_read_all_data" in script
    assert "REPLICATION PASSWORD" not in script.replace("NOREPLICATION", "")
