from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "truenas" / "diagnose-stuck-apps.sh"


def test_stuck_app_diagnostic_is_read_only_and_bounded() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "--check" in text
    assert "NABLA_STUCK_APP_QUERY_TIMEOUT_SECONDS" in text
    assert "core.get_jobs" in text
    assert "docker ps -a" in text
    assert "docker inspect" in text
    assert "docker logs --tail" in text
    assert "diagnose-sentry.sh --check" in text
    assert "diagnose-wazuh.sh --check" in text
    assert "required catalog dependencies" in text
    assert "service-topology.json" in text

    for forbidden in (
        "app.start",
        "app.stop",
        "app.update",
        "app.redeploy",
        "docker restart",
        "docker rm",
        "docker image prune",
        "docker system prune",
    ):
        assert forbidden not in text

    syntax = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr


def test_grafana_storage_repair_is_bounded() -> None:
    script = (
        ROOT / "scripts" / "truenas" / "repair-grafana-storage-permissions.sh"
    ).read_text(encoding="utf-8")

    assert "--check" in script
    assert "--apply" in script
    assert "/mnt/cpool/loki" in script
    assert "/mnt/cpool/tempo" in script
    assert "docker image inspect" in script
    assert "chown" in script
    assert "chown -R" not in script
    assert "docker restart" not in script
    assert "app.redeploy" not in script

    syntax = subprocess.run(
        ["bash", "-n", str(ROOT / "scripts" / "truenas" / "repair-grafana-storage-permissions.sh")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr

def test_sentry_migrator_credential_diagnostic_is_bounded_and_secret_safe() -> None:
    path = ROOT / "scripts" / "truenas" / "diagnose-sentry-migrator-credential.sh"
    script = path.read_text(encoding="utf-8")

    assert "/mnt/cpool/sentry/.env.migrator.secrets" in script
    assert "SENTRY_MIGRATOR_CHECK_TIMEOUT_SECONDS" in script
    assert "system.users" in script
    assert "SELECT 1" in script
    assert "NABLA_MIGRATOR_PASSWORD" in script
    assert "CLICKHOUSE_PASSWORD is missing/empty" in script
    assert 'cat "${SECRET_FILE}"' not in script
    assert 'echo "${password}"' not in script

    syntax = subprocess.run(
        ["bash", "-n", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr


def test_sentry_migrator_reconcile_is_scoped_and_secret_safe() -> None:
    path = ROOT / "scripts" / "truenas" / "reconcile-sentry-migrator-credential.sh"
    script = path.read_text(encoding="utf-8")

    assert "--check" in script
    assert "--apply" in script
    assert "CREATE USER IF NOT EXISTS sentry_migrator" in script
    assert "ALTER USER sentry_migrator" in script
    assert "GRANT ALL ON sentry.* TO sentry_migrator" in script
    assert "GRANT CREATE WORKLOAD, DROP WORKLOAD ON *.* TO sentry_migrator" in script
    assert "openssl rand -hex 32" in script
    assert "ClickHouse admin identity is usable" in script
    assert "^[0-9a-fA-F]{64}$" in script
    assert "docker exec -i" in script
    assert "NABLA_MIGRATOR_PASSWORD" not in script
    assert "docker restart" not in script
    assert "app.redeploy" not in script
    assert "DROP DATABASE" not in script
    assert "DROP USER" not in script

    syntax = subprocess.run(
        ["bash", "-n", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr


def test_openrag_opensearch_secret_reconcile_is_bounded() -> None:
    path = ROOT / "scripts" / "truenas" / "reconcile-openrag-opensearch-secret.sh"
    script = path.read_text(encoding="utf-8")

    assert "--check" in script
    assert "--apply" in script
    assert "/mnt/cpool/openrag/.env.secrets" in script
    assert "apps/opensearch/.env" in script
    assert "OPENSEARCH_PASSWORD" in script
    assert "without printing it" in script
    assert "docker restart" not in script
    assert "app.redeploy" not in script

    syntax = subprocess.run(
        ["bash", "-n", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr


def test_vaultwarden_legacy_adapter_keeps_https_origin() -> None:
    compose = (ROOT / "apps" / "vaultwarden" / "compose.yml").read_text(
        encoding="utf-8"
    )
    assert 'BW_HOST: "https://vaultwarden.albandrieu.com"' in compose
    assert 'BW_HOST: "http://vaultwarden"' not in compose
