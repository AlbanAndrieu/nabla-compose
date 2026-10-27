"""Offline OpenRAG safe-start checks: no TrueNAS, network or private documents."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-openrag-startup.sh"

@pytest.mark.skipif(shutil.which("jq") is None, reason="jq required by TrueNAS preflight")
@pytest.mark.parametrize("state,valid_secret,symlink,docker_health,expected_exit,expected", [
    ("STOPPED", True, False, "healthy", 1, "start_authorization=REQUIRED"),
    ("RUNNING", True, False, "healthy", 0, "OPENRAG_STARTUP_PREFLIGHT=READY_FOR_OPERATOR_REVIEW"),
    ("RUNNING", False, False, "healthy", 1, "secret_OPENSEARCH_PASSWORD=missing"),
    ("RUNNING", True, True, "healthy", 1, "OpenRAG secret symlink is not the reviewed canonical migration target"),
    ("RUNNING", True, False, "unhealthy", 1, "health=unhealthy"),
    ("RUNNING", True, False, "starting", 1, "health=starting"),
    ("RUNNING", True, False, "missing", 1, "state=unknown health=unknown"),
])
def test_startup_preflight_does_not_mutate_or_reveal_secrets(
    tmp_path: Path, state: str, valid_secret: bool, symlink: bool,
    docker_health: str, expected_exit: int, expected: str
) -> None:
    corpus = tmp_path / "private-corpus"
    corpus.mkdir()
    secret = tmp_path / ".env.secrets"
    keys = ["LANGFLOW_KEY", "LITELLM_IDE_API_KEY", "OPENRAG_ENCRYPTION_KEY"]
    if valid_secret:
        keys.append("OPENSEARCH_PASSWORD")
    sentinel = "PRIVATE-OPENRAG-NEVER-PRINT"
    secret.write_text("".join(f"{key}={sentinel}\n" for key in keys),
                      encoding="utf-8")
    secret.chmod(0o600)
    secret_used = secret
    if symlink:
        secret_used = tmp_path / ".env.link"
        secret_used.symlink_to(secret)
    mocks = tmp_path / "bash-env"
    mocks.write_text(
        'midclt() { printf \'[{"id":"openrag","state":"%s"}]\' "$MOCK_APP_STATE"; }\n'
        'timeout() { shift; "$@"; }\n'
        'zfs() { printf "%s\\tyes\\n" "$OPENRAG_BABABOU_SOURCE"; }\n'
        'curl() {\n'
        '  case "$*" in\n'
        '    *7860*) printf "200" ;;\n'
        '    *4000*) printf "200" ;;\n'
        '    *5001*) printf "000" ;;\n'
        '    *) return 99 ;;\n'
        '  esac\n'
        '}\n'
        'docker() {\n'
        '  [[ "$MOCK_DOCKER_HEALTH" != missing ]] || return 1\n'
        '  printf "running|%s\\n" "$MOCK_DOCKER_HEALTH"\n'
        '}\n',
        encoding="utf-8",
    )
    env = dict(os.environ)
    env.update({
        "MOCK_APP_STATE": state,
        "MOCK_DOCKER_HEALTH": docker_health,
        "OPENRAG_SECRET_FILE": str(secret_used),
        "OPENRAG_BABABOU_SOURCE": str(corpus),
        "OPENRAG_ZFS_DATASET": "synthetic/bababou",
        "BASH_ENV": str(mocks),
    })
    result = subprocess.run(
        ["bash", str(SCRIPT), "--check"], capture_output=True, text=True,
        env=env, check=False, timeout=15
    )
    output = result.stdout + result.stderr
    assert result.returncode == expected_exit, output
    assert expected in output
    if state == "RUNNING":
        assert "openrag_component=openrag-backend" in output
        assert "openrag_component=openrag-frontend" in output
    assert "docling_ingestion_prerequisite=unavailable" in output
    assert "litellm_liveliness=HTTP_200 models_auth=not_tested" in output
    assert sentinel not in output
    assert "app.start" not in output
    assert "OPENRAG_STARTUP_PREFLIGHT" in output


def test_preflight_is_wired_into_local_first_and_both_migration_sections() -> None:
    wrapper = (ROOT / "scripts/truenas/migration-diagnostic-sections.sh").read_text(
        encoding="utf-8"
    )
    just = (ROOT / "justfile").read_text(encoding="utf-8")
    gate = ("run_check openrag-startup bash "
            "scripts/truenas/diagnose-openrag-startup.sh --check")
    assert wrapper.count(gate) == 2  # `ai` and `openrag` sections in the registry
    assert "truenas-openrag-startup-check:" in just
    assert "truenas-openrag-startup-test:" in just
    assert "tests/test_openrag_startup_preflight.py" in just


def test_non_truenas_context_is_not_misreported_as_openrag_failure(
    tmp_path: Path,
) -> None:
    # No middleware executable on PATH: the script must not read host secrets
    # or attempt any remote TrueNAS or Docker operation.
    empty_path = tmp_path / "bin"
    empty_path.mkdir()
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), "--check"],
        capture_output=True, text=True, check=False,
        env=os.environ | {"PATH": str(empty_path)},
        timeout=8,
    )
    assert result.returncode == 2
    assert "host_context=NOT_TRUENAS_OR_MIDCLT_NOT_IN_PATH" in result.stderr
    assert "OPENRAG_STARTUP_PREFLIGHT=NOT_RUN" in result.stderr
    assert "secret_" not in result.stdout


def test_preflight_fails_closed_for_mutating_flags() -> None:
    run = subprocess.run(
        ["bash", str(SCRIPT), "--apply"], capture_output=True, text=True,
        check=False
    )
    assert run.returncode == 2
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("docker start", "app.start", "app.redeploy", "rm -rf",
                      "chown -R", "chmod -R", "docker compose up"):
        assert forbidden not in source
    syntax = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert syntax.returncode == 0, syntax.stderr
