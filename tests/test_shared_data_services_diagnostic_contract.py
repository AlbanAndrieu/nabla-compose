"""Shared PostgreSQL/Redis diagnostic contract (offline, fake docker)."""

from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-shared-data-services.sh"
SECRET = "redis-test-secret-value"

FAKE_DOCKER = """#!/usr/bin/env bash
case "$1" in
  inspect)
    if [[ "$2" == redis && "${FAKE_REDIS_DOWN:-0}" == 1 ]]; then printf 'false\\n'; else printf 'true\\n'; fi ;;
  exec)
    if [[ "$2" == ix-postgres-postgres-1 ]]; then exit 0; fi
    IFS= read -r auth
    [[ "${auth}" == "${FAKE_REDIS_PASSWORD}" ]] || exit 1
    case "${*: -1}" in
      PING) printf 'PONG\\n' ;;
      keyspace) printf 'db0:keys=3,expires=0,avg_ttl=0\\n' ;;
    esac ;;
  *) exit 1 ;;
esac
"""


def _run(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    # TrueNAS /tmp can be noexec: executable fake CLIs must live on the repo FS.
    with tempfile.TemporaryDirectory(prefix=".shared-data-mock-", dir=ROOT) as temp_dir:
        docker = Path(temp_dir) / "docker"
        docker.write_text(FAKE_DOCKER)
        docker.chmod(0o755)
        env = os.environ | {
            "PATH": f"{temp_dir}:{os.environ['PATH']}",
            "FAKE_REDIS_PASSWORD": SECRET,
            "DIAG_COLOR": "never",
            "DIAG_ICONS": "never",
        } | extra_env
        return subprocess.run(
            ["bash", str(SCRIPT)], cwd=ROOT, env=env, capture_output=True, text=True, check=False,
        )


def test_healthy_services_pass_without_leaking_the_redis_secret() -> None:
    result = _run({"REDIS_AUTH": SECRET})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: PostgreSQL accepte les connexions" in result.stdout
    assert "OK: Redis authentifié : PING → PONG" in result.stdout
    assert "db0:keys=3" in result.stdout
    assert "checks: warnings=0 failures=0 unknown=0" in result.stdout
    assert SECRET not in result.stdout + result.stderr


def test_missing_secret_is_a_warning_not_a_failure() -> None:
    result = _run({"REDIS_AUTH": ""})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "WARN: Redis : secret indisponible" in result.stdout


def test_stopped_redis_fails_the_diagnostic() -> None:
    result = _run({"REDIS_AUTH": SECRET, "FAKE_REDIS_DOWN": "1"})
    assert result.returncode == 1
    assert "FAIL: Redis absent ou arrêté" in result.stdout
    assert "checks: warnings=0 failures=1 unknown=0" in result.stdout
