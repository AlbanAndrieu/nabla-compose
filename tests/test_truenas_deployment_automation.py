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
    # Every bootstrap tool is pinned; uv and PyYAML follow mise.toml/pyproject.
    assert "uv@latest" not in script
    assert 'UV_VERSION="${NABLA_UV_VERSION:-0.13.0}"' in script
    assert 'uv = "0.13.0"' in (ROOT / "mise.toml").read_text(encoding="utf-8")
    assert '"uv@${UV_VERSION}"' in script
    assert 'PYYAML_VERSION="${NABLA_PYYAML_VERSION:-6.0.3}"' in script
    assert '"PyYAML==6.0.3"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"PyYAML==${PYYAML_VERSION}"' in script
    assert '"shellcheck@${SHELLCHECK_VERSION}"' in script
    assert "--no-config" in script
    assert "export MISE_LOCKFILE=false" in script
    assert 'trust "${ROOT}/mise.toml"' not in script
    assert 'PYTEST_VERSION="${NABLA_PYTEST_VERSION:-9.1.1}"' in script
    assert 'JUST_VERSION="${NABLA_JUST_VERSION:-1.58.0}"' in script
    assert '"just@${JUST_VERSION}"' in script
    assert 'PYTHON_DOTENV_VERSION="${NABLA_PYTHON_DOTENV_VERSION:-1.2.4}"' in script
    assert 'JSONSCHEMA_VERSION="${NABLA_JSONSCHEMA_VERSION:-4.22.0}"' in script
    assert '"pre-commit==${PRE_COMMIT_VERSION}" "pytest==${PYTEST_VERSION}"' in script
    assert '"python-dotenv==${PYTHON_DOTENV_VERSION}" "jsonschema==${JSONSCHEMA_VERSION}"' in script
    assert '"jsonschema==${JSONSCHEMA_VERSION}" PyYAML' not in script
    assert 'if [[ -x "${DEV_VENV}/bin/python" ]]' in script
    assert "Reusing existing virtual environment" in script
    assert 'uv venv --clear --python "${PYTHON_BIN}" "${DEV_VENV}"' in script
    assert 'ln -sfn "${JUST_BIN}" "${DEV_VENV}/bin/just"' in script
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
    assert "never redeploys a TrueNAS App" in doc
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


def test_docker_prune_cron_uses_single_line_without_escaped_spaces() -> None:
    document = DOC.read_text(encoding="utf-8")
    canonical = (
        "env NABLA_DOCKER_IMAGE_PRUNE_MIN_AGE_HOURS=168 "
        "bash /mnt/cpool/compose/nabla-compose/scripts/truenas/prune-docker-images.sh --apply"
    )
    assert "command=" + canonical in document
    assert "env: ‘ ’: No such file or directory" in document
    assert "not yet" in document.lower() or "not confirmed repaired" in document
    script = DOCKER_PRUNE.read_text(encoding="utf-8")
    assert "docker image prune -f --filter" in script
    assert "flock -n 9" in script
    assert "PREPARING | PREPARED | RESUMED" in script
    assert "docker system prune" not in script


def _stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/usr/bin/env bash\n" + body + "\n", encoding="utf-8")
    path.chmod(0o755)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_cron_reports_runtime_and_gates_fastapi_on_cloud_health(tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    checkout = tmp_path / "checkout"
    _git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(seed))
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    _git(seed, "add", "README.md")
    _git(seed, "commit", "-q", "-m", "seed")
    _git(seed, "push", "-q", "origin", "HEAD:master")
    _git(tmp_path, "clone", "-q", "-b", "master", str(origin), str(checkout))
    (seed / "apps" / "foo").mkdir(parents=True)
    (seed / "apps" / "foo" / "compose.yml").write_text("services: {}\n", encoding="utf-8")
    _git(seed, "add", "apps")
    _git(seed, "commit", "-q", "-m", "feat(foo): add app")
    _git(seed, "push", "-q", "origin", "HEAD:master")

    # A deployed FastAPI Sample checkout behind its remote master.
    sample_remote = tmp_path / "sample.git"
    sample_seed = tmp_path / "sample-seed"
    _git(tmp_path, "init", "-q", "--bare", "-b", "master", str(sample_remote))
    _git(tmp_path, "clone", "-q", str(sample_remote), str(sample_seed))
    (sample_seed / "app.py").write_text("v1\n", encoding="utf-8")
    _git(sample_seed, "add", "app.py")
    _git(sample_seed, "commit", "-q", "-m", "v1")
    _git(sample_seed, "push", "-q", "origin", "HEAD:master")
    _git(tmp_path, "clone", "-q", str(sample_remote), str(checkout / "apps" / "fastapi-sample"))
    (sample_seed / "app.py").write_text("v2\n", encoding="utf-8")
    _git(sample_seed, "commit", "-q", "-am", "v2")
    _git(sample_seed, "push", "-q", "origin", "HEAD:master")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir, "logger", "exit 0")
    _stub(bin_dir, "sudo", 'echo "sudo must not run: $*" >&2; exit 97')
    _stub(
        bin_dir,
        "midclt",
        """echo '[{"id":"foo","state":"RUNNING"},{"id":"bar","state":"STOPPED"}]'""",
    )
    _stub(
        bin_dir,
        "docker",
        """case "$1" in
  info) exit 0 ;;
  ps) echo abc123 ;;
  inspect) echo "/ix-foo-web-1|ix-foo|$(date -u +%Y-%m-%dT%H:%M:%S.000000000Z)|0" ;;
esac""",
    )
    _stub(
        bin_dir,
        "curl",
        """for arg in "$@"; do url="$arg"; done
case "$url" in
  */healthz) echo '{"status":"degraded","components":{"api":{"status":"healthy"}},"checks":{"openstack_me":{"reachable":false}}}' ;;
  *) printf 200 ;;
esac""",
    )

    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "NABLA_CRON_LOCK_FILE": str(tmp_path / "cron.lock"),
        "NABLA_CRON_FASTAPI_REMOTE": str(sample_remote),
        "NABLA_CRON_LOG_DIR": str(tmp_path / "logs"),
    }
    result = subprocess.run(
        ["bash", str(CRON), str(checkout)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout
    assert "Hourly sync of" in out
    assert "1 new commit(s):" in out
    assert "feat(foo): add app" in out
    assert "Updating files" not in out + result.stderr
    assert "Impacted TrueNAS Apps for " in out
    assert "redeploy in dependency order: none" in out
    assert "skipped: foo (not in the service catalog)" in out
    assert "TrueNAS Apps: RUNNING=1, STOPPED=1" in out
    assert "Apps not RUNNING: bar (STOPPED)" in out
    assert "ix-foo-web-1: TrueNAS App foo" in out
    assert "FastAPI Cloud is not fully healthy (status=degraded, failing: openstack_me)" in out
    assert "sudo must not run" not in result.stderr
    assert _git(checkout, "rev-parse", "HEAD") == _git(seed, "rev-parse", "HEAD")
