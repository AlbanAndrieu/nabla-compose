from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / "scripts" / "truenas" / "bootstrap-repository-storage.sh"
SCANOPY = ROOT / "scripts" / "truenas" / "deploy-scanopy.sh"


def test_repository_storage_bootstrap_discovers_compose_dataset_roots() -> None:
    script = STORAGE.read_text(encoding="utf-8")

    assert 'POOL="${NABLA_ZFS_POOL:-cpool}"' in script
    assert "apps/*/compose.yml" in script
    assert 'grep -RhoE "${CANONICAL_MOUNT//\\//\\/}/[A-Za-z0-9._-]+"' in script
    assert 'zfs create -p "${dataset}"' in script
    assert 'zfs list -H -o name "${dataset}"' in script
    assert 'zfs get -H -o value mountpoint "${dataset}"' in script
    assert "--check | --apply" in script


def test_scanopy_deploy_reconciles_dataset_and_truenas_custom_app() -> None:
    script = SCANOPY.read_text(encoding="utf-8")

    assert "bootstrap-repository-storage.sh --apply" in script
    assert "bootstrap-repository-storage.sh --check" in script
    assert 'SECRETS_FILE="${SCANOPY_SECRETS_FILE:-/mnt/cpool/scanopy/.env.secrets}"' in script
    assert "POSTGRES_PASSWORD" in script
    assert "SCANOPY_DATABASE_URL" in script
    assert 'compose_path="${ROOT}/apps/scanopy/compose.yml"' in script
    assert "midclt call -j app.create" in script
    assert "midclt call -j app.update" in script
    assert "custom_compose_config_string" in script
    assert "custom_compose_config" in script
    assert "include:" in script
