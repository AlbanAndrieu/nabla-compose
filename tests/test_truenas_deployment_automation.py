from __future__ import annotations

import json
from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[1]
CRON = ROOT / "scripts" / "cron.sh"
BOOTSTRAP = ROOT / "bootstrap" / "compose.yaml"
TRUENAS_DOCO = ROOT / "docker-compose-truenas.yml"
WORKSTATION_COMPOSE = ROOT / "docker-compose.yml"
DEV_TOOLS = ROOT / "scripts" / "truenas" / "bootstrap-dev-tools.sh"
DOCKER_PRUNE = ROOT / "scripts" / "truenas" / "prune-docker-images.sh"
DOC = ROOT / "docs" / "truenas-deployment-automation.md"
ROOT_CATALOG = ROOT / "catalog" / "catalog-info.yaml"
GENERATED_SERVICES = ROOT / "catalog" / "services.json"
GENERATED_TOPOLOGY = ROOT / "catalog" / "service-topology.json"


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
    assert "docker image prune" not in script

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


def test_doco_cd_catalog_authority_is_owned_by_truenas_compose() -> None:
    truenas = yaml.safe_load(TRUENAS_DOCO.read_text(encoding="utf-8"))
    workstation = yaml.safe_load(WORKSTATION_COMPOSE.read_text(encoding="utf-8"))

    truenas_doco = truenas["services"]["doco-cd"]
    self_metadata = truenas_doco["x-nabla"]
    assert self_metadata["id"] == "doco-cd"
    assert self_metadata["criticality"] == "medium"
    assert truenas_doco["labels"]["com.albandrieu.nabla.entity-ref"] == (
        "component:default/doco-cd"
    )
    assert [port["name"] for port in truenas_doco["ports"]] == [
        "webhook",
        "metrics",
    ]

    assert truenas_doco["cap_drop"] == ["ALL"]
    assert truenas_doco["security_opt"] == ["no-new-privileges:true"]

    assert "x-nabla" not in workstation["services"]["doco-cd"]
    assert "labels" not in workstation["services"]["doco-cd"]

    entities = [
        entity
        for entity in yaml.safe_load_all(ROOT_CATALOG.read_text(encoding="utf-8"))
        if isinstance(entity, dict)
    ]
    doco_entity = next(
        entity
        for entity in entities
        if entity.get("kind") == "Component"
        and entity.get("metadata", {}).get("name") == "doco-cd"
    )
    assert doco_entity["spec"]["dependsOn"] == [
        "component:default/docker-socket-proxy"
    ]

    generated = json.loads(GENERATED_SERVICES.read_text(encoding="utf-8"))
    doco_service = next(
        service for service in generated["services"] if service["id"] == "doco-cd"
    )
    assert doco_service["sourcePath"] == "docker-compose-truenas.yml"
    assert doco_service["runtime"]["networks"] == [
        "default",
        "intranet",
        "secrets-backend",
    ]
    topology = json.loads(GENERATED_TOPOLOGY.read_text(encoding="utf-8"))
    doco_node = next(node for node in topology["nodes"] if node["id"] == "doco-cd")
    assert doco_node["sourcePath"] == "docker-compose-truenas.yml"
    assert doco_node["runtime"]["networks"] == [
        "default",
        "intranet",
        "secrets-backend",
    ]
    doco_relations = {
        (relation["type"], relation["target"]): relation
        for relation in topology["relations"]
        if relation["source"] == "doco-cd"
    }
    assert doco_relations[("hostedBy", "docker")]["evidence"] == [
        "docker-compose-truenas.yml:doco-cd.x-nabla.runtime.containerService"
    ]
    assert doco_relations[("consumesApi", "docker-socket-proxy")]["evidence"] == [
        "docker-compose-truenas.yml:DOCKER_HOST=tcp://docker-socket-proxy:2375"
    ]


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
    assert 'SHELLCHECK_VERSION="${NABLA_SHELLCHECK_VERSION:-0.11.0}"' in script
    assert "uv@latest" in script
    assert '"shellcheck@${SHELLCHECK_VERSION}"' in script
    assert "--no-config" in script
    assert "export MISE_LOCKFILE=false" in script
    assert 'trust "${ROOT}/mise.toml"' not in script
    assert 'PYTEST_VERSION="${NABLA_PYTEST_VERSION:-9.1.1}"' in script
    assert '"pre-commit==${PRE_COMMIT_VERSION}" "pytest==${PYTEST_VERSION}" PyYAML' in script
    assert 'if [[ -x "${DEV_VENV}/bin/python" ]]' in script
    assert "Reusing existing virtual environment" in script
    assert 'uv venv --clear --python "${PYTHON_BIN}" "${DEV_VENV}"' in script
    assert 'ln -sfn "${SHELLCHECK_BIN}" "${DEV_VENV}/bin/shellcheck"' in script
    assert "The agent quality gate automatically prepends this venv when it exists" in script
    agent_gate = (ROOT / "scripts" / "agent-quality-gate.sh").read_text(
        encoding="utf-8"
    )
    assert 'DEV_VENV="${NABLA_TRUENAS_DEV_VENV:-${HOME}/.cache/nabla-compose/dev-venv}"' in agent_gate
    assert 'export PATH="${DEV_VENV}/bin:${PATH}"' in agent_gate
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
    updater = (ROOT / "scripts" / "truenas" / "update-fastapi-sample.sh").read_text(
        encoding="utf-8",
    )
    assert "pfsense_auth_smoke" in updater
    assert "--url https://home.albandrieu.com:10443" in updater
    assert "deployment remains accepted because pfSense is optional diagnostic evidence" in updater
    assert 'release_ref=false' in updater
    assert '[[ "${REF}" =~ ^v?[0-9]+[.][0-9]+[.][0-9]+$ ]]' in updater
    assert "pull-only mode requires a version ref" in updater
    assert "Moving/source ref %s selected; building target commit %s locally" in updater
    syntax = subprocess.run(
        ["bash", "-n", str(ROOT / "scripts" / "truenas" / "update-fastapi-sample.sh")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr
    assert "bootstrap-dev-tools.sh" in doc


def test_docker_image_cleanup_is_separate_bounded_maintenance() -> None:
    script = DOCKER_PRUNE.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")

    assert "NABLA_DOCKER_IMAGE_PRUNE_MIN_AGE_HOURS" in script
    assert "168" in script
    assert 'docker image prune -f --filter "until=' in script
    assert "PREPARING | PREPARED | RESUMED" in script
    assert "forbidden until VERIFIED" in script
    assert "audit-docker-storage-debt.sh" in script
    assert "docker system prune" not in script
    assert "docker network prune" not in script
    assert "docker volume prune" not in script
    assert "docker container prune" not in script
    assert "docker image prune -a" not in script

    assert "separate root job" in doc
    assert "minute=37 hour=4" in doc
    assert "NABLA_DOCKER_IMAGE_PRUNE_MIN_AGE_HOURS=168" in doc

    syntax = subprocess.run(
        ["bash", "-n", str(DOCKER_PRUNE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr
