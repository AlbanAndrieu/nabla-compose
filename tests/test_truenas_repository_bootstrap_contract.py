from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / "scripts" / "truenas" / "bootstrap-repository-storage.sh"
ENV_FILES = ROOT / "scripts" / "truenas" / "bootstrap-repository-env-files.sh"
RUNTIME = ROOT / "scripts" / "truenas" / "bootstrap-repository-runtime.sh"
SCANOPY = ROOT / "scripts" / "truenas" / "deploy-scanopy.sh"
AUTOKUMA = ROOT / "scripts" / "truenas" / "deploy-autokuma.sh"
AUTOKUMA_TOKEN = ROOT / "scripts" / "truenas" / "bootstrap-autokuma-token.sh"
DOCLING = ROOT / "scripts" / "truenas" / "deploy-docling.sh"
JOPLIN = ROOT / "scripts" / "truenas" / "deploy-joplin.sh"


def test_repository_storage_bootstrap_uses_active_owned_bind_mounts() -> None:
    script = STORAGE.read_text(encoding="utf-8")

    assert 'POOL="${NABLA_ZFS_POOL:-cpool}"' in script
    assert "git ls-files 'apps/*/compose.yml'" in script
    assert 'if [[ "${app}" == "code" && "${root}" != "code" ]]' in script
    assert "dataset_preset()" in script
    assert "compose | logs | model | secrets" in script
    assert 'printf \'APPS\\n\'' in script
    assert "midclt call pool.dataset.create" in script
    assert '"share_type":"%s"' in script
    assert "dataset_is_empty()" in script
    assert "Empty direct child datasets not owned" in script
    assert 'zfs create -p "${dataset}"' not in script
    assert "--check | --apply" in script


def test_repository_env_bootstrap_centralizes_materializations() -> None:
    script = ENV_FILES.read_text(encoding="utf-8")

    assert 'SECRETS_DATASET="${NABLA_SECRETS_DATASET:-${POOL}/secrets}"' in script
    assert 'RUNTIME_ROOT="${NABLA_RUNTIME_ENV_ROOT:-${SECRETS_ROOT}/runtime}"' in script
    assert 'BOOTSTRAP_ROOT="${NABLA_BOOTSTRAP_ENV_ROOT:-${SECRETS_ROOT}/bootstrap}"' in script
    assert "git ls-files 'apps/*/compose.yml'" in script
    assert "implicit-local" in script
    assert "legacy-root" in script
    assert "install -o root -g root -m 600" in script
    assert 'ln -s "${canonical}" "${source}"' in script
    assert "check_private_directory" in script
    assert 'if [[ "${MODE}" == "--check" ]]' in script
    assert "--check | --apply" in script


def test_repository_runtime_bootstrap_orders_storage_before_env_files() -> None:
    script = RUNTIME.read_text(encoding="utf-8")

    storage = "bootstrap-repository-storage.sh"
    env_files = "bootstrap-repository-env-files.sh"
    assert storage in script
    assert env_files in script
    assert script.index(storage) < script.index(env_files)


def assert_canonical_custom_app_deploy(script_path: Path, app: str) -> str:
    script = script_path.read_text(encoding="utf-8")
    canonical = "/mnt/cpool/compose/nabla-compose"

    assert canonical in script
    assert "bootstrap-repository-runtime.sh --apply" in script
    assert "bootstrap-repository-runtime.sh --check" in script
    assert "midclt call -j app.create" in script
    assert "midclt call -j app.update" in script
    assert f"apps/{app}/compose.yml" in script
    assert "custom_compose_config_string" in script
    assert "custom_compose_config" in script
    assert "include:" in script
    return script


def test_scanopy_deploy_reconciles_runtime_and_custom_app() -> None:
    script = assert_canonical_custom_app_deploy(SCANOPY, "scanopy")

    assert "/mnt/cpool/secrets/runtime/scanopy/.env.secrets" in script
    assert "POSTGRES_PASSWORD" in script
    assert "SCANOPY_DATABASE_URL" in script


def test_autokuma_deploy_reconciles_runtime_and_custom_app() -> None:
    script = assert_canonical_custom_app_deploy(AUTOKUMA, "autokuma")
    token_script = AUTOKUMA_TOKEN.read_text(encoding="utf-8")

    assert "/mnt/cpool/secrets/runtime/autokuma/.env.secrets" in script
    assert "/mnt/cpool/secrets/runtime/autokuma" in token_script
    assert "AUTOKUMA__KUMA__URL" in script
    assert "AUTOKUMA__KUMA__AUTH_TOKEN" in script
    assert "generated-monitors.json" in script


def test_docling_deploy_requires_no_service_secret_file() -> None:
    script = assert_canonical_custom_app_deploy(DOCLING, "docling")

    assert ".env.secrets" not in script


def test_joplin_deploy_requires_postgres_secret_and_custom_app() -> None:
    script = assert_canonical_custom_app_deploy(JOPLIN, "joplin")

    assert "/mnt/cpool/secrets/runtime/joplin/.env.secrets" in script
    assert "POSTGRES_PASSWORD" in script
    assert "root:root mode 0600" in script
    assert "shared PostgreSQL role/database joplin must already exist" in script
