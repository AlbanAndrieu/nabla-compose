from pathlib import Path
import stat
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "truenas" / "diagnose-stuck-apps.sh"


def test_stuck_app_diagnostic_is_read_only_and_bounded() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "--check" in text
    assert "NABLA_STUCK_APP_QUERY_TIMEOUT_SECONDS" in text
    assert "core.get_jobs" in text
    assert "lib/docker.sh" in text
    assert "docker_compose_project_container_ids" in text
    assert "docker_container_runtime_summary" in text
    assert "pid=%s" in text
    assert "docker logs --tail" in text
    assert "recover-sentry-deploying.sh --check" in text
    assert "diagnose-wazuh.sh --check" in text
    assert "diagnose-nginx-proxy-manager.sh --check" in text
    assert "no repository-owned OpenArchiver Compose exists" in text
    assert "no repository-owned Paperless-ngx Compose exists" in text
    assert "required catalog dependencies" in text
    assert "service-topology.json" in text
    assert "NABLA_REBOOT_STATE_ROOT" in text
    assert "apps-before.json" in text
    assert "resume-apps.txt" in text
    assert "intentional-stopped.txt" in text
    assert "preexisting-failed.txt" in text
    assert "reboot_context=" in text
    assert "pre_reboot_state=" in text
    assert "expected-resume" in text
    assert "preexisting-failed" in text
    assert "intentional-stopped" in text
    assert "regressions=%d deferred=%d" in text
    assert '.state == "ERROR"' in text

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


def test_nginx_proxy_manager_diagnostic_is_read_only_and_value_blind() -> None:
    path = ROOT / "scripts" / "truenas" / "diagnose-nginx-proxy-manager.sh"
    script = path.read_text(encoding="utf-8")

    assert "--check" in script
    assert "jc21/nginx-proxy-manager:2.15.0" in script
    assert "30020|30021|30022" in script
    assert "/mnt/cpool/npm" in script
    assert "database.sqlite" in script
    assert "recent lifecycle jobs (arguments intentionally omitted)" in script
    assert ".Config.Env" not in script
    assert "app.start" not in script
    assert "app.stop" not in script
    assert "app.update" not in script
    assert "app.redeploy" not in script
    assert "docker restart" not in script
    assert "docker rm" not in script

    mode = path.stat().st_mode
    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH

    syntax = subprocess.run(
        ["bash", "-n", str(path)],
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

def test_sentry_runtime_clickhouse_credential_reconcile_is_bounded() -> None:
    diagnostic = (
        ROOT
        / "scripts"
        / "truenas"
        / "diagnose-sentry-runtime-clickhouse-credential.sh"
    )
    reconcile = (
        ROOT
        / "scripts"
        / "truenas"
        / "reconcile-sentry-runtime-clickhouse-credential.sh"
    )
    diagnostic_text = diagnostic.read_text(encoding="utf-8")
    reconcile_text = reconcile.read_text(encoding="utf-8")

    assert "/mnt/cpool/secrets/runtime/sentry/.env.secrets" in diagnostic_text
    assert "CLICKHOUSE_READONLY_PASSWORD" in diagnostic_text
    assert "CLICKHOUSE_TRACE_PASSWORD" in diagnostic_text
    assert "system.users" in diagnostic_text
    assert "NABLA_SENTRY_CLICKHOUSE_PASSWORD" in diagnostic_text
    assert 'cat "${SECRET_FILE}"' not in diagnostic_text
    assert 'echo "${password}"' not in diagnostic_text

    assert "CREATE USER IF NOT EXISTS sentry" in reconcile_text
    assert "ALTER USER sentry" in reconcile_text
    assert "GRANT SELECT, INSERT, ALTER UPDATE, ALTER DELETE ON sentry.* TO sentry" in reconcile_text
    assert "GRANT SELECT ON system.tables TO sentry" in reconcile_text
    assert "SENTRY_RUNTIME_CLICKHOUSE_RECONCILE_TIMEOUT_SECONDS" in reconcile_text
    assert "openssl rand" not in reconcile_text
    assert "docker restart" not in reconcile_text
    assert "app.redeploy" not in reconcile_text
    assert "DROP DATABASE" not in reconcile_text
    assert "DROP USER" not in reconcile_text

    for path in (diagnostic, reconcile):
        syntax = subprocess.run(
            ["bash", "-n", str(path)],
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


def test_sentry_system_secret_reconcile_is_bounded() -> None:
    path = ROOT / "scripts" / "truenas" / "reconcile-sentry-system-secret.sh"
    script = path.read_text(encoding="utf-8")

    assert "--check" in script
    assert "--apply" in script
    assert "/mnt/cpool/sentry/.env.secrets" in script
    assert "/mnt/cpool/secrets/runtime/sentry/.env.secrets" in script
    assert "SENTRY_SECRET_KEY" in script
    assert "SENTRY_SYSTEM_SECRET_KEY" in script
    assert "RELAY_ID" in script
    assert "RELAY_PUBLIC_KEY" in script
    assert "RELAY_SECRET_KEY" in script
    assert "ghcr.io/getsentry/relay:26.8.0" in script
    assert "credentials generate --stdout" in script
    assert "--network none" in script
    assert "openssl rand -hex 32" in script
    assert "recover-sentry-deploying.sh --apply" in script
    assert "value not printed" in script
    assert "values not printed" in script
    assert "docker restart" not in script
    assert "app.redeploy" not in script
    assert "cat " not in script

    syntax = subprocess.run(
        ["bash", "-n", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr


def test_sentry_deploying_recovery_is_targeted_and_acceptance_gated() -> None:
    path = ROOT / "scripts" / "truenas" / "recover-sentry-deploying.sh"
    script = path.read_text(encoding="utf-8")

    assert "--check" in script
    assert "--apply" in script
    assert "--finalize" in script
    assert "reconcile-sentry-system-secret.sh" in script
    assert "reconcile-sentry-runtime-clickhouse-credential.sh" in script
    assert "reconcile-sentry-migrator-credential.sh" in script
    assert 'midclt call -j app.redeploy "${APP_ID}"' in script
    assert "truenas_wait_app_running" in script
    assert "diagnose-sentry.sh" in script
    assert "smoke-sentry-event.sh" in script
    assert "--restage sentry" in script
    assert "--check sentry" in script
    assert script.index("--restage sentry") < script.index("app.redeploy")
    assert "--finalize sentry" in script
    assert "pre-finalization end-to-end ingestion smoke" in script
    assert "--reset-offsets" not in script
    assert "docker restart" not in script
    assert "DROP DATABASE" not in script
    assert "kafka-topics --delete" not in script
    assert path.stat().st_mode & stat.S_IXUSR
    assert path.stat().st_mode & stat.S_IXGRP
    assert path.stat().st_mode & stat.S_IXOTH

    syntax = subprocess.run(
        ["bash", "-n", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr


def test_sentry_diagnostic_surfaces_system_secret_and_migration_errors() -> None:
    script = (ROOT / "scripts" / "truenas" / "diagnose-sentry.sh").read_text(
        encoding="utf-8"
    )

    assert "Sentry system-secret preflight" in script
    assert "reconcile-sentry-system-secret.sh --check" in script
    assert "recent_migration_error_evidence" in script
    assert "SENTRY_MIGRATION_LOG_TAIL" in script
    assert "steady-state service is exited: service=%s container=%s exit=%s" in script
    assert "steady-state service is restarting: service=%s container=%s exit=%s restarts=%s" in script
    assert "outcomes-billing" in script
    assert "SENTRY_RESTART_LOG_TAIL" in script
    assert "Sentry Relay credential preflight" in script
    assert "RELAY_ID" in script
    assert "RELAY_PUBLIC_KEY" in script
    assert "RELAY_SECRET_KEY" in script
    assert "missing key names" in script
