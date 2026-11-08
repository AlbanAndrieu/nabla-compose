from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / "scripts" / "truenas" / "bootstrap-repository-storage.sh"
ENV_FILES = ROOT / "scripts" / "truenas" / "bootstrap-repository-env-files.sh"
RUNTIME = ROOT / "scripts" / "truenas" / "bootstrap-repository-runtime.sh"
SCANOPY = ROOT / "scripts" / "truenas" / "deploy-scanopy.sh"
SCANOPY_POSTGRES = ROOT / "scripts" / "truenas" / "bootstrap-scanopy-postgres.sh"
SCANOPY_COMPOSE = ROOT / "apps" / "scanopy" / "compose.yml"
AUTOKUMA = ROOT / "scripts" / "truenas" / "deploy-autokuma.sh"
AUTOKUMA_TOKEN = ROOT / "scripts" / "truenas" / "bootstrap-autokuma-token.sh"
AUTOKUMA_COMPOSE = ROOT / "apps" / "autokuma" / "compose.yml"
DOCLING = ROOT / "scripts" / "truenas" / "deploy-docling.sh"
JOPLIN = ROOT / "scripts" / "truenas" / "deploy-joplin.sh"
JOPLIN_POSTGRES = ROOT / "scripts" / "truenas" / "bootstrap-joplin-postgres.sh"
FIRST_WAVE = ROOT / "scripts" / "truenas" / "accept-runtime-env-first-wave.sh"


def test_repository_storage_bootstrap_uses_active_owned_bind_mounts() -> None:
    script = STORAGE.read_text(encoding="utf-8")

    assert 'POOL="${NABLA_ZFS_POOL:-cpool}"' in script
    assert "git ls-files 'apps/*/compose.yml'" in script
    assert 'if [[ "${app}" == "code" && "${root}" != "code" ]]' in script
    assert "dataset_preset()" in script
    assert "compose | logs | model | secrets | iso | k8s | k8s/*" in script
    assert "midclt call pool.dataset.create" in script
    assert '"share_type":"%s"' in script
    assert "dataset_is_empty()" in script
    assert 'mapfile -t descendants < <(zfs list -H -o name -r "${dataset}"' in script
    assert 'dataset_is_empty "${dataset}" "${mountpoint}"' in script
    assert "Empty direct child datasets not owned" in script
    assert 'zfs create -p "${dataset}"' not in script
    assert "--check | --apply" in script


def test_repository_storage_bootstrap_includes_platform_prerequisites() -> None:
    script = STORAGE.read_text(encoding="utf-8")

    assert '[[ -z "${APP_FILTER}" || "${APP_FILTER}" == "dsomm" ]]' in script
    assert 'declared_paths["dsomm"]="APPS"' in script

    for relative in (
        "secrets",
        "k8s",
        "k8s/talos-vms",
        "k8s/nfs",
        "k8s/csi",
        "iso",
    ):
        assert f'declared_paths["{relative}"]="GENERIC"' in script

    assert 'if [[ -z "${APP_FILTER}" ]]' in script
    assert "apps + platform prerequisites" in script
    assert "repository-owned platform prerequisites" in script
    assert "owned_top_level" in script


def test_repository_env_bootstrap_centralizes_materializations() -> None:
    script = ENV_FILES.read_text(encoding="utf-8")

    assert 'SECRETS_DATASET="${NABLA_SECRETS_DATASET:-${POOL}/secrets}"' in script
    assert 'RUNTIME_ROOT="${NABLA_RUNTIME_ENV_ROOT:-${SECRETS_ROOT}/runtime}"' in script
    assert 'BOOTSTRAP_ROOT="${NABLA_BOOTSTRAP_ENV_ROOT:-${SECRETS_ROOT}/bootstrap}"' in script
    assert "git ls-files 'apps/*/compose.yml'" in script
    assert "implicit-local" in script
    assert "legacy-root" in script
    assert "install -o root -g root -m 600" in script
    assert 'ln -s "${target}" "${source}"' in script
    assert "check_private_directory" in script
    assert 'if [[ "${MODE}" == "--check" ]]' in script
    assert "continuing read-only migration preview so unrelated migration debt remains visible" in script
    assert "--check | --apply | --stage-existing | --restage | --finalize" in script
    assert "--restage requires an explicit app filter" in script
    assert "restage verification failed" in script


def test_repository_env_bootstrap_handles_zero_legacy_sources() -> None:
    script = ENV_FILES.read_text(encoding="utf-8")
    # Bash 5.3 rejects empty associative-array subscripts.
    assert '[[ -n "${source}" ]] || continue' in script
    assert 'app="${source_app["${source}"]}"' in script


def test_repository_env_bootstrap_rejects_empty_secret_placeholders() -> None:
    script = ENV_FILES.read_text(encoding="utf-8")

    assert "requires_nonempty_materialization()" in script
    assert ".env.secrets | .env.*.secrets" in script
    assert "is an empty secret placeholder; populate/render it before staging" in script
    assert "empty-placeholder; populate/render secret material before acceptance" in script
    assert '[[ ! -s "${primary}" ]]' in script
    assert '[[ ! -s "${target}" ]]' in script


def test_repository_env_finalize_allows_only_empty_placeholder_replacement() -> None:
    script = ENV_FILES.read_text(encoding="utf-8")

    assert '[[ ! -s "${source}" && -s "${target}" ]]' in script
    assert "finalized empty-placeholder compatibility-link" in script
    assert "empty-placeholder -> %s canonical non-empty; finalize pending" in script
    assert "This is the only non-byte-identical finalization case allowed" in script
    assert "migration conflict:" in script


def test_repository_runtime_bootstrap_orders_storage_before_env_files() -> None:
    script = RUNTIME.read_text(encoding="utf-8")

    storage = "bootstrap-repository-storage.sh"
    env_files = "bootstrap-repository-env-files.sh"
    assert storage in script
    assert env_files in script
    assert script.index(storage) < script.index(env_files)
    assert 'if [[ "${MODE}" == "--check" ]]' in script
    assert '|| status=1' in script


APP_DEPLOY_LIB = ROOT / "scripts" / "lib" / "app-deploy.sh"
TRUENAS_LIB = ROOT / "scripts" / "lib" / "truenas.sh"
APP_POSTGRES = ROOT / "scripts" / "truenas" / "bootstrap-app-postgres.sh"
POSTGRES_LIB = ROOT / "scripts" / "lib" / "postgres.sh"


def assert_canonical_custom_app_deploy(script_path: Path, app: str) -> str:
    script = script_path.read_text(encoding="utf-8")
    canonical = "/mnt/cpool/compose/nabla-compose"

    assert canonical in script
    assert 'bootstrap-repository-runtime.sh --apply "${APP_ID}"' in script
    assert 'bootstrap-repository-runtime.sh --check "${APP_ID}"' in script
    assert f"apps/{app}/compose.yml" in script
    if "app_deploy_reconcile" in script:
        # Shared deploy contract: reconciliation lives in lib/app-deploy.sh on
        # top of lib/truenas.sh, with the same middleware payloads.
        assert "lib/app-deploy.sh" in script
        assert "app_deploy_mode" in script
        assert "app_deploy_check_report" in script
        reconcile = APP_DEPLOY_LIB.read_text(encoding="utf-8") + TRUENAS_LIB.read_text(encoding="utf-8")
        assert "truenas_reconcile_custom_app" in reconcile
        assert "NABLA_RUNTIME_CHANGE_APPROVED" in reconcile
    else:
        reconcile = script
    # Jobs go through the shared truenas_job_compact helper (midclt call -j).
    assert "truenas_job_compact app.create" in reconcile
    assert "truenas_job_compact app.update" in reconcile
    assert "custom_compose_config_string" in reconcile
    assert "custom_compose_config" in reconcile
    assert "include:" in reconcile
    return script


def test_scanopy_deploy_reconciles_runtime_shared_postgres_and_custom_app() -> None:
    script = assert_canonical_custom_app_deploy(SCANOPY, "scanopy")
    compose = SCANOPY_COMPOSE.read_text(encoding="utf-8")

    assert "/mnt/cpool/secrets/runtime/scanopy/.env.secrets" in script
    assert "POSTGRES_PASSWORD" in script
    assert "SCANOPY_DATABASE_URL" in script
    assert "bootstrap-scanopy-postgres.sh --check" in script
    assert "shared PostgreSQL dependency verified" in script
    assert "scanopy-postgres:" not in compose
    assert "target: postgresql" in compose
    assert "/mnt/cpool/scanopy/postgres" not in compose


def assert_shared_postgres_bootstrap(wrapper: Path, app: str) -> None:
    """The per-app wrappers delegate to the consolidated, idempotent bootstrap."""
    wrapper_text = wrapper.read_text(encoding="utf-8")
    script = APP_POSTGRES.read_text(encoding="utf-8")
    library = POSTGRES_LIB.read_text(encoding="utf-8")

    assert f'bootstrap-app-postgres.sh" "${{1:---check}}" {app}' in wrapper_text
    assert f"{app.upper()}_SECRETS_FILE" in wrapper_text
    assert 'EXPECTED_HOST="${NABLA_POSTGRES_HOST:-172.17.0.24}"' in script
    assert 'EXPECTED_PORT="${NABLA_POSTGRES_PORT:-5432}"' in script
    assert "secrets_assert_file" in script
    assert "secrets_get_value" in script
    assert "com.docker.compose.project=ix-postgres" in library
    assert "CREATE ROLE %I LOGIN PASSWORD %L" in library
    assert "ALTER ROLE %I PASSWORD %L" in library
    assert "CREATE DATABASE %I OWNER %I" in library
    assert "ALTER DATABASE %I OWNER TO %I" in library
    assert "dedicated role cannot authenticate to the shared PostgreSQL database" in script
    assert "shared PostgreSQL ready app=" in script
    assert 'printf "%s" "${db_password}"' not in script


def test_scanopy_shared_postgres_bootstrap_is_idempotent_and_fail_closed() -> None:
    assert_shared_postgres_bootstrap(SCANOPY_POSTGRES, "scanopy")
    script = APP_POSTGRES.read_text(encoding="utf-8")

    assert 'URL_KEY="SCANOPY_DATABASE_URL"' in script
    assert "password differs from ${SECRET_KEY}" in script


def test_autokuma_deploy_reconciles_runtime_and_custom_app() -> None:
    script = assert_canonical_custom_app_deploy(AUTOKUMA, "autokuma")
    token_script = AUTOKUMA_TOKEN.read_text(encoding="utf-8")
    compose = AUTOKUMA_COMPOSE.read_text(encoding="utf-8")

    assert "/mnt/cpool/secrets/runtime/autokuma/.env.secrets" in script
    assert "/mnt/cpool/secrets/runtime/autokuma" in token_script
    assert "AUTOKUMA__KUMA__URL:" in compose
    assert "AUTOKUMA__KUMA__AUTH_TOKEN" in script
    assert "generated-monitors.json" in script
    assert "endpoint remains non-secret Compose configuration" in token_script


def test_docling_deploy_requires_no_service_secret_file() -> None:
    script = assert_canonical_custom_app_deploy(DOCLING, "docling")

    assert ".env.secrets" not in script


def test_joplin_deploy_requires_postgres_secret_and_custom_app() -> None:
    script = assert_canonical_custom_app_deploy(JOPLIN, "joplin")

    assert "/mnt/cpool/secrets/runtime/joplin/.env.secrets" in script
    assert "POSTGRES_PASSWORD" in script
    assert "root:root mode 0600" in script
    assert "bootstrap-joplin-postgres.sh --check" in script
    assert "shared PostgreSQL dependency verified" in script


def test_joplin_shared_postgres_bootstrap_is_idempotent_and_fail_closed() -> None:
    assert_shared_postgres_bootstrap(JOPLIN_POSTGRES, "joplin")


def test_first_wave_acceptance_stages_before_finalize() -> None:
    script = FIRST_WAVE.read_text(encoding="utf-8")

    assert "--check | --stage | --accept" in script
    # --accept deploys; the deployers default to read-only --check.
    assert "deploy-scanopy.sh --apply" in script
    assert "deploy-joplin.sh --apply" in script
    assert "NABLA_RUNTIME_CHANGE_APPROVED" in script
    assert 'stage_service "${app}"' in script
    assert 'deploy_service "${app}"' in script
    assert 'functional_probe "${app}"' in script
    assert 'bootstrap-repository-env-files.sh --finalize "${app}"' in script
    assert script.index('functional_probe "${app}"') < script.index(
        'bootstrap-repository-env-files.sh --finalize "${app}"'
    )
