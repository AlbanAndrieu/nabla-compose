from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
CRON = ROOT / "scripts" / "cron.sh"
BOOTSTRAP = ROOT / "bootstrap" / "compose.yaml"
TRUENAS_DOCO = ROOT / "docker-compose-truenas.yml"
WORKSTATION_COMPOSE = ROOT / "docker-compose.yml"
DEV_TOOLS = ROOT / "scripts" / "truenas" / "bootstrap-dev-tools.sh"
DOC = ROOT / "docs" / "truenas-deployment-automation.md"


def test_cron_is_branch_bounded_and_non_destructive() -> None:
    script = CRON.read_text(encoding="utf-8")

    assert 'DEPLOY_BRANCH="${NABLA_CRON_BRANCH:-master}"' in script
    assert "flock -n 9" in script
    assert 'CURRENT_BRANCH="$(git symbolic-ref --quiet --short HEAD' in script
    assert 'if [[ "${CURRENT_BRANCH}" != "${DEPLOY_BRANCH}" ]]' in script
    assert 'git -c fetch.recurseSubmodules=false fetch origin "${DEPLOY_BRANCH}"' in script
    assert 'git -c submodule.recurse=false merge --ff-only "origin/${DEPLOY_BRANCH}"' in script
    assert "git reset --hard" not in script
    assert "--ignore-submodules=all" in script
    assert "Runtime deployment remains owned by the already-running Doco-CD instance" in script
    assert "docker compose" not in script

    syntax = subprocess.run(
        ["bash", "-n", str(CRON)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr


def test_live_truenas_doco_cd_uses_canonical_master_deployments() -> None:
    compose = TRUENAS_DOCO.read_text(encoding="utf-8")

    assert "reference: master" in compose
    assert "apps/vaultwarden/compose.yml" in compose
    assert "apps/garage/compose.yml" in compose
    assert "compose_file: apps/vaultwarden/compose.yml" in compose
    assert "compose_file: apps/garage/compose.yml" in compose
    assert "compose_file: vaultwarden/compose.yml" not in compose
    assert "compose_file: garage/compose.yml" not in compose
    assert "apps/sample/compose.yml" not in compose
    assert "ghcr.io/kimdre/doco-cd:0.85.1" in compose
    assert "ghcr.io/kimdre/doco-cd:latest" not in compose
    assert "SECRET_PROVIDER: webhook" in compose
    assert "DOCKER_HOST: tcp://docker-socket-proxy:2375" in compose
    assert ".doco-cd/1pw_token" not in compose


def test_workstation_compose_is_not_the_truenas_doco_cd_owner() -> None:
    compose = WORKSTATION_COMPOSE.read_text(encoding="utf-8")
    assert compose.startswith(
        "# Workstation-only Compose root. TrueNAS Doco-CD uses docker-compose-truenas.yml."
    )


def test_bootstrap_doco_cd_polls_real_master_with_pinned_image() -> None:
    compose = BOOTSTRAP.read_text(encoding="utf-8")

    assert "reference: master" in compose
    assert "reference: main" not in compose
    assert "ghcr.io/kimdre/doco-cd:0.85.1" in compose
    assert "ghcr.io/kimdre/doco-cd:latest" not in compose
    assert "interval: 3600" in compose


def test_truenas_dev_tooling_is_user_space_only() -> None:
    script = DEV_TOOLS.read_text(encoding="utf-8")

    assert "https://mise.run" in script
    assert '${HOME}/.local/bin/mise' in script
    assert 'PRE_COMMIT_VERSION="${NABLA_PRE_COMMIT_VERSION:-4.6.2}"' in script
    assert "uv@latest" in script
    assert "--no-config" in script
    assert 'trust "${ROOT}/mise.toml"' not in script
    assert '"pre-commit==${PRE_COMMIT_VERSION}" pytest PyYAML' in script
    assert 'PATH="${DEV_VENV}/bin:\\$PATH" bash scripts/agent-quality-gate.sh --fix' in script
    assert "install-operator-tools.sh --check" in script
    assert "apt install" not in script
    assert "apt-get" not in script
    assert "sudo " not in script

    syntax = subprocess.run(
        ["bash", "-n", str(DEV_TOOLS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr


def test_deployment_automation_documents_sample_ownership_boundary() -> None:
    doc = DOC.read_text(encoding="utf-8")

    assert "Layer 0" in doc
    assert "Git synchronization only" in doc
    assert "Layer 1" in doc
    assert "docker-compose-truenas.yml" in doc
    assert "docker-compose.yml,docker-compose.override.yml" in doc
    assert "Doco-CD must not gain an implicit Sample deployment target" in doc
    assert "update-fastapi-sample.sh" in doc
    assert "bootstrap-dev-tools.sh" in doc
