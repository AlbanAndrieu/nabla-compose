from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_BOOTSTRAP = ROOT / "scripts" / "truenas" / "bootstrap-repository-env-files.sh"
STORAGE_BOOTSTRAP = ROOT / "scripts" / "truenas" / "bootstrap-repository-storage.sh"
RUNTIME_BOOTSTRAP = ROOT / "scripts" / "truenas" / "bootstrap-repository-runtime.sh"
RUNTIME_LAYOUT = ROOT / "docs" / "truenas-runtime-layout.md"
COMPOSE_SKILL = ROOT / ".agents" / "skills" / "docker-compose-orchestration" / "SKILL.md"
SECRETS_SKILL = ROOT / ".agents" / "skills" / "homelab-secrets" / "SKILL.md"
ROADMAP = ROOT / "docs" / "roadmap.md"
FIRST_WAVE = ROOT / "scripts" / "truenas" / "accept-runtime-env-first-wave.sh"
HOMEASSISTANT = ROOT / "apps" / "homeassistant" / "compose.yml"
DEPLOY_HELPERS = {
    "scanopy": ROOT / "scripts" / "truenas" / "deploy-scanopy.sh",
    "joplin": ROOT / "scripts" / "truenas" / "deploy-joplin.sh",
    "autokuma": ROOT / "scripts" / "truenas" / "deploy-autokuma.sh",
    "docling": ROOT / "scripts" / "truenas" / "deploy-docling.sh",
}


def test_runtime_env_migration_is_staged_before_finalize() -> None:
    script = ENV_BOOTSTRAP.read_text(encoding="utf-8")

    assert "--check | --apply | --finalize" in script
    assert "stage verified root-only canonical copies; keep old paths intact" in script
    assert "staged from %s; legacy path left intact" in script
    assert 'if [[ "${MODE}" == "--finalize" ]]' in script
    assert 'ln -s "${target}" "${source}"' in script
    assert "run --apply first" in script
    assert "no existing source can stage it" in script


def test_project_dotenv_cannot_collide_with_service_env_file() -> None:
    script = ENV_BOOTSTRAP.read_text(encoding="utf-8")

    assert 'if [[ "${kind}" == "implicit-local" && "${name}" == ".env" ]]' in script
    assert 'name=".env.compose"' in script
    assert "multiple sources differ" in script
    assert "cmp -s" in script


def test_app_scoped_runtime_bootstrap_stays_bounded() -> None:
    runtime = RUNTIME_BOOTSTRAP.read_text(encoding="utf-8")
    storage = STORAGE_BOOTSTRAP.read_text(encoding="utf-8")

    assert 'APP_FILTER="${2:-}"' in runtime
    assert 'bootstrap-repository-storage.sh "${MODE}" "${APP_FILTER}"' in runtime
    assert 'bootstrap-repository-env-files.sh "${MODE}" "${APP_FILTER}"' in runtime
    assert 'APP_FILTER="${2:-}"' in storage
    assert 'app_selected "${app}" || continue' in storage
    assert "App-scoped checks deliberately" in storage

    for app, path in DEPLOY_HELPERS.items():
        helper = path.read_text(encoding="utf-8")
        assert 'bootstrap-repository-runtime.sh --apply "${APP_ID}"' in helper, app
        assert 'bootstrap-repository-runtime.sh --check "${APP_ID}"' in helper, app


def test_true_nas_runtime_layout_is_documented_and_skill_enforced() -> None:
    layout = RUNTIME_LAYOUT.read_text(encoding="utf-8")
    compose_skill = COMPOSE_SKILL.read_text(encoding="utf-8")
    secrets_skill = SECRETS_SKILL.read_text(encoding="utf-8")
    roadmap = ROADMAP.read_text(encoding="utf-8")

    canonical_runtime = "/mnt/cpool/secrets/runtime/<service>/"
    bootstrap = "/mnt/cpool/secrets/bootstrap/vaultwarden/"

    for text in (layout, compose_skill, secrets_skill):
        assert canonical_runtime in text
        assert bootstrap in text

    assert "application-owned persistent data only" in layout
    assert "TrueNAS **Apps** preset" in layout
    assert "TrueNAS **Generic**" in layout
    assert "Whenever a service is created or materially modified" in compose_skill
    assert "Existing legacy" in compose_skill
    assert "--finalize <service>" in secrets_skill
    assert "TrueNAS storage + runtime secret normalization" in roadmap


def test_value_blind_env_inventory_classifies_secret_risk() -> None:
    script = (
        ROOT / "scripts" / "truenas" / "inventory-runtime-env-files.sh"
    ).read_text(encoding="utf-8")

    assert "WORKTREE_SECRET" in script
    assert "UNSAFE_SECRET" in script
    assert "EMPTY_SECRET" in script
    assert "OK_SECRET" in script
    assert "STATE" in script
    assert 'cat -- "${path}"' not in script
    assert 'grep ' not in script


def test_sample_uses_canonical_runtime_env_files() -> None:
    compose = (ROOT / "apps" / "sample" / "compose.yml").read_text(encoding="utf-8")

    assert "/mnt/cpool/secrets/runtime/sample/.env" in compose
    assert "/mnt/cpool/secrets/runtime/sample/.env.secrets" in compose
    assert "/mnt/cpool/sample/.env" not in compose
    assert "/mnt/cpool/sample/.env.secrets" not in compose
    assert 'MCP_OPS_REQUIRE_KEY: "true"' in compose


def test_homeassistant_does_not_require_missing_dotenv() -> None:
    compose = HOMEASSISTANT.read_text(encoding="utf-8")

    assert "env_file:" not in compose
    assert "      - .env" not in compose


def test_first_wave_runtime_acceptance_is_bounded_and_finalizes_after_health() -> None:
    script = FIRST_WAVE.read_text(encoding="utf-8")

    for app in ("scanopy", "joplin", "autokuma"):
        assert app in script
    assert "--check | --stage | --accept" in script
    assert "--accept is deliberately one service at a time" in script
    assert 'bootstrap-repository-runtime.sh --apply "${app}"' in script
    assert 'bootstrap-repository-runtime.sh --check "${app}"' in script
    assert 'verify-app-runtime-health.sh' in script
    assert 'bootstrap-repository-env-files.sh --finalize "${app}"' in script
    assert script.index('deploy_service "${app}"') < script.index(
        'bootstrap-repository-env-files.sh --finalize "${app}"'
    )
    assert "Uptime Kuma must exist and be RUNNING before acceptance" in script


def test_runtime_layout_blocks_new_legacy_env_file_apps() -> None:
    import yaml

    legacy_allowlist = {
        "code",
        "mongo",
        "sentry",
        "nexus",
        "homarr",
        "ollama",
        "dozzle",
        "garage",
        "pihole",
        "bichon",
        "wazuh",
        "graylog",
        "openrag",
        "traefik",
        "scrutiny",
        "keycloak",
        "akvorado",
        "langfuse",
        "postgres",
        "langflow",
        "crowdsec",
        "opensearch",
        "clickhouse",
        "litellm",
        "sentry-clickhouse",
    }
    observed_legacy: set[str] = set()

    for compose_path in sorted((ROOT / "apps").glob("*/compose.yml")):
        app = compose_path.parent.name
        compose = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
        for service in (compose.get("services") or {}).values():
            env_files = service.get("env_file") or []
            if isinstance(env_files, str):
                env_files = [env_files]
            for entry in env_files:
                path = entry.get("path", "") if isinstance(entry, dict) else entry
                if not path:
                    continue
                canonical_runtime = f"/mnt/cpool/secrets/runtime/{app}/"
                canonical_bootstrap = "/mnt/cpool/secrets/bootstrap/vaultwarden/"
                if path.startswith(canonical_runtime) or path.startswith(
                    canonical_bootstrap
                ):
                    continue
                observed_legacy.add(app)

    assert observed_legacy <= legacy_allowlist, (
        "new legacy env_file app(s) must use /mnt/cpool/secrets/runtime/<service>/: "
        f"{sorted(observed_legacy - legacy_allowlist)}"
    )
