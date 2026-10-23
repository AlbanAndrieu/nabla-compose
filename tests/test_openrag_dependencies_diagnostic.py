"""Offline OpenRAG dependency status tests; no TrueNAS access."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-openrag-dependencies.sh"


@pytest.mark.parametrize("backend,frontend,langflow,expected,exit_code", [
    ("running healthy 0 0", "created none 0 0", "running healthy 0 0",
     "frontend created despite healthy backend", 1),
    ("running starting 0 0", "created none 0 0", "running healthy 0 0",
     "backend not running+healthy", 1),
    ("running healthy 0 0", "running healthy 0 0", "running healthy 0 0",
     "OK: OpenRAG backend/frontend", 0),
    ("running healthy 0 0", "created none 0 0", "exited unhealthy 2 3",
     "shared Langflow/OpenSearch prerequisite not running", 1),
])
def test_dependency_states_are_classified_without_redeployment(
    tmp_path, noexec_safe_bash_mocks, backend, frontend, langflow,
    expected, exit_code
):
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    docker = fakebin / "docker"
    docker.write_text(
        chr(10).join((
            "#!/usr/bin/env bash",
            'case "${@: -1}" in',
            '  openrag-backend) printf "%s\\n" "$TEST_BACKEND" ;;',
            '  openrag-frontend) printf "%s\\n" "$TEST_FRONTEND" ;;',
            '  langflow) printf "%s\\n" "$TEST_LANGFLOW" ;;',
            '  opensearch) echo "running healthy 0 0" ;;',
            '  docling) echo "missing none - -" ;;',
            '  *) exit 99 ;;',
            'esac',
            "",
        )),
        encoding="utf-8",
    )
    docker.chmod(0o600)
    env = os.environ.copy()
    env.update({
        "PATH": str(fakebin) + os.pathsep + env["PATH"],
        "TEST_BACKEND": backend,
        "TEST_FRONTEND": frontend,
        "TEST_LANGFLOW": langflow,
        "NABLA_DIAGNOSTIC_OFFLINE": "1",
    })
    env = noexec_safe_bash_mocks(env, "docker")
    result = subprocess.run(
        ["bash", str(SCRIPT), "--check"], env=env, capture_output=True,
        text=True, check=False, timeout=10, cwd=ROOT
    )
    output = result.stdout + result.stderr
    assert result.returncode == exit_code, output
    assert expected in output
    assert "PRIVATE-TOKEN" not in output


def test_openrag_diagnostic_is_read_only_bash():
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True,
        text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "docker restart", "docker start", "app.redeploy", "app.update",
        "docker inspect .Config.Env", "docker logs", "rm -rf",
        "kubectl delete", "curl -k", "docker compose up",
    ):
        assert forbidden not in source


def test_migration_ai_acceptance_runs_openrag_dependency_gate():
    wrapper = (ROOT / "scripts/truenas/finish-migrations-20261024.sh").read_text(
        encoding="utf-8"
    )
    just = (ROOT / "justfile").read_text(encoding="utf-8")
    assert ("run_check openrag-dependencies bash "
            "scripts/truenas/diagnose-openrag-dependencies.sh --check") in wrapper
    assert "truenas-openrag-dependencies-check:" in just
    assert "tests/test_openrag_dependencies_diagnostic.py" in just


def test_openrag_compose_label_fallback_resolves_trueNAS_containers(
    tmp_path, noexec_safe_bash_mocks
):
    """Resolve ix-openrag and ix-opensearch project service labels offline."""
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    docker = fakebin / "docker"
    docker.write_text(chr(10).join((
        "#!/usr/bin/env bash",
        'if [[ "$1" == inspect ]]; then',
        '  last="${@: -1}"',
        '  if [[ "$last" =~ ^[a-f0-9]{12}$ && "$*" == *"--format"* ]]; then',
        '    echo "running healthy 0 0"; exit 0',
        '  fi',
        '  if [[ "$last" == langflow ]]; then',
        '    if [[ "$*" == *"--format"* ]]; then echo "running healthy 0 0"; fi',
        '    exit 0',
        '  fi',
        '  exit 1',
        'fi',
        'if [[ "$1" == ps ]]; then',
        '  case "$*" in',
        '    *ix-openrag*openrag-backend*) echo aaaaaaaaaaaa ;;',
        '    *ix-openrag*openrag-frontend*) echo bbbbbbbbbbbb ;;',
        '    *ix-opensearch*opensearch*) echo cccccccccccc ;;',
        '  esac',
        '  exit 0',
        'fi',
        'exit 99',
        "",
    )), encoding="utf-8")
    docker.chmod(0o600)
    env = os.environ.copy()
    env["PATH"] = str(fakebin) + os.pathsep + env["PATH"]
    env["NABLA_DIAGNOSTIC_OFFLINE"] = "1"
    env = noexec_safe_bash_mocks(env, "docker")
    result = subprocess.run(
        ["bash", str(SCRIPT), "--check"], env=env, text=True,
        capture_output=True, check=False, timeout=10, cwd=ROOT
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "openrag-backend status=running health=healthy" in result.stdout
    assert "openrag-frontend status=running health=healthy" in result.stdout
    assert "opensearch status=running health=healthy" in result.stdout
