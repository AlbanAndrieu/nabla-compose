from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_BOOTSTRAP = ROOT / "scripts" / "truenas" / "bootstrap-repository-env-files.sh"
RUNTIME_LAYOUT = ROOT / "docs" / "truenas-runtime-layout.md"
COMPOSE_SKILL = ROOT / ".agents" / "skills" / "docker-compose-orchestration" / "SKILL.md"
SECRETS_SKILL = ROOT / ".agents" / "skills" / "homelab-secrets" / "SKILL.md"
ROADMAP = ROOT / "docs" / "roadmap.md"


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
