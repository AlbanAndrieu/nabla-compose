from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "apps" / "cyberbro" / "compose.yml"
BOOTSTRAP = ROOT / "scripts" / "truenas" / "bootstrap-cyberbro-env.sh"
DEPLOY = ROOT / "scripts" / "truenas" / "deploy-cyberbro.sh"
DIAGNOSE = ROOT / "scripts" / "truenas" / "diagnose-cyberbro.sh"


def test_cyberbro_uses_canonical_storage_and_runtime_env_files() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")

    assert "/mnt/cpool/cyberbro/data:/app/data" in compose
    assert "/mnt/cpool/cyberbro/logs:/var/log/cyberbro" in compose
    assert "path: /mnt/cpool/secrets/runtime/cyberbro/.env" in compose
    assert "path: /mnt/cpool/secrets/runtime/cyberbro/.env.secrets" in compose
    assert compose.count("required: true") >= 2


def test_cyberbro_env_bootstrap_materializes_config_and_optional_secrets() -> None:
    script = BOOTSTRAP.read_text(encoding="utf-8")

    assert "/mnt/cpool/secrets/runtime/cyberbro" in script
    assert 'install -o root -g root -m 600' in script
    assert "render_from_bitwarden.py" in script
    assert "API_CACHE_TIMEOUT=" in script
    assert "VIRUSTOTAL=" in script
    assert "root:root 600" in script


def test_cyberbro_deploy_uses_supported_truenas_custom_app_flow() -> None:
    script = DEPLOY.read_text(encoding="utf-8")

    assert 'bootstrap-repository-storage.sh --apply "${APP_ID}"' in script
    assert "bootstrap-cyberbro-env.sh --apply" in script
    assert "docker compose" in script
    assert "--no-interpolate" in script
    assert "--no-env-resolution" in script
    assert "midclt call -j app.create" in script
    assert "midclt call -j app.update" in script
    assert "custom_compose_config_string" in script
    assert "custom_compose_config" in script
    assert "diagnose-cyberbro.sh" in script
    assert "curl -fsS" in script


def test_cyberbro_deploy_reconciles_generated_observability_consumers() -> None:
    script = DEPLOY.read_text(encoding="utf-8")

    assert "generate-service-topology.py --check" in script
    assert "generate-service-consumers.py --check" in script
    assert "deploy-autokuma.sh" in script
    assert "uptime-kuma" in script
    assert "gatus" in script
    assert "homarr" in script
    assert "Prometheus not redeployed" in script


def test_cyberbro_diagnostic_collects_bounded_runtime_evidence() -> None:
    script = DIAGNOSE.read_text(encoding="utf-8")

    assert "midclt call app.query" in script
    assert "core.get_jobs" in script
    assert "docker inspect" in script
    assert "docker logs --tail 80" in script
    assert "/var/log/middlewared.log" in script
    assert "journalctl -u docker" in script
    assert "no database dependency" in script
    assert "curl -fsS" in script
