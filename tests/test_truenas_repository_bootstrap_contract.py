from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / "scripts" / "truenas" / "bootstrap-repository-storage.sh"
ENV_FILES = ROOT / "scripts" / "truenas" / "bootstrap-repository-env-files.sh"
RUNTIME = ROOT / "scripts" / "truenas" / "bootstrap-repository-runtime.sh"
SCANOPY = ROOT / "scripts" / "truenas" / "deploy-scanopy.sh"
AUTOKUMA = ROOT / "scripts" / "truenas" / "deploy-autokuma.sh"
DOCLING = ROOT / "scripts" / "truenas" / "deploy-docling.sh"
JOPLIN = ROOT / "scripts" / "truenas" / "deploy-joplin.sh"


def test_repository_storage_bootstrap_discovers_compose_dataset_roots() -> None:
    script = STORAGE.read_text(encoding="utf-8")

    assert 'POOL="${NABLA_ZFS_POOL:-cpool}"' in script
    assert "apps/*/compose.yml" in script
    assert 'grep -RhoE "${CANONICAL_MOUNT//\\//\\/}/[A-Za-z0-9._-]+"' in script
    assert 'zfs create -p "${dataset}"' in script
    assert 'zfs list -H -o name "${dataset}"' in script
    assert 'zfs get -H -o value mountpoint "${dataset}"' in script
    assert "--check | --apply" in script


def test_repository_env_bootstrap_discovers_only_declared_env_files() -> None:
    script = ENV_FILES.read_text(encoding="utf-8")

    assert "env_file:" in script
    assert "/mnt/cpool/" in script
    assert "git ls-files 'apps/*/compose.yml'" in script
    assert "install -o root -g root -m 600 /dev/null" in script
    assert "stat -c '%u:%g %a'" in script
    assert "root:root mode=0600" in script
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

    assert 'SECRETS_FILE="${SCANOPY_SECRETS_FILE:-/mnt/cpool/scanopy/.env.secrets}"' in script
    assert "POSTGRES_PASSWORD" in script
    assert "SCANOPY_DATABASE_URL" in script


def test_autokuma_deploy_reconciles_runtime_and_custom_app() -> None:
    script = assert_canonical_custom_app_deploy(AUTOKUMA, "autokuma")

    assert "/mnt/cpool/autokuma/.env.secrets" in script
    assert "AUTOKUMA__KUMA__URL" in script
    assert "AUTOKUMA__KUMA__AUTH_TOKEN" in script
    assert "generated-monitors.json" in script


def test_docling_deploy_requires_no_service_secret_file() -> None:
    script = assert_canonical_custom_app_deploy(DOCLING, "docling")

    assert ".env.secrets" not in script


def test_joplin_deploy_requires_postgres_secret_and_custom_app() -> None:
    script = assert_canonical_custom_app_deploy(JOPLIN, "joplin")

    assert "/mnt/cpool/joplin/.env.secrets" in script
    assert "POSTGRES_PASSWORD" in script
    assert "root:root mode 0600" in script
    assert "shared PostgreSQL role/database joplin must already exist" in script
