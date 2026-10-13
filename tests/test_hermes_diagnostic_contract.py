"""Hermes security inventory stays read-only and emits no runtime secrets."""

import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-hermes-agent.sh"


@pytest.mark.parametrize(
    ("privileged", "mount", "health", "expected_status", "expected_text"),
    [
        ("false", "/opt/data|true", "healthy", 0, "summary failures=0"),
        ("true", "/opt/data|true", "healthy", 1, "Privileged container"),
        ("false", "/var/run/docker.sock|true", "healthy", 1, "Docker socket mounted"),
        ("false", "/opt/data|true", "unhealthy", 1, "Hermes container health=unhealthy"),
    ],
)
def test_hermes_check_does_not_mutate_or_leak(
    tmp_path, privileged, mount, health, expected_status, expected_text
):
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    binaries = {
        "midclt": """#!/bin/sh
printf '[{"id":"hermes-agent","state":"RUNNING"}]\\n'
""",
        "docker": """#!/bin/sh
case "$*" in
  *'{{.State.Status}}'*) echo "${FAKE_STATUS:-running}" ;;
  *'{{if .State.Health}}'*) echo "${FAKE_HEALTH:-healthy}" ;;
  *'{{.Config.User}}'*) echo 10000:10000 ;;
  *'{{.HostConfig.Privileged}}'*) echo "${FAKE_PRIVILEGED:-false}" ;;
  *'{{.HostConfig.ReadonlyRootfs}}'*) echo true ;;
  *'{{.HostConfig.NetworkMode}}'*) echo bridge ;;
  *'{{range .Mounts}}'*) echo "${FAKE_MOUNT:-/opt/data|true}" ;;
  *'{{.Image}}'*) echo sha256:fixture ;;
  *'container={{.Name}}'*) echo 'container=/ix-hermes-agent-hermes-agent-1 status=running health=healthy image=hermes:fixture' ;;
  *) exit 0 ;;
esac
""",
        "curl": "#!/bin/sh\nexit 0\n",
    }
    for name, content in binaries.items():
        program = fakebin / name
        program.write_text(content, encoding="utf-8")
        program.chmod(0o755)
    env = os.environ | {
        "PATH": f"{fakebin}:{os.environ['PATH']}",
        "FAKE_PRIVILEGED": privileged,
        "FAKE_MOUNT": mount,
        "FAKE_HEALTH": health,
        "TEST_SECRET_NOT_FOR_OUTPUT": "token-super-secret-fixture",
    }
    result = subprocess.run(
        ["bash", str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
        check=False,
    )
    assert result.returncode == expected_status, result.stdout + result.stderr
    assert expected_text in result.stdout
    assert "token-super-secret-fixture" not in result.stdout + result.stderr
    assert "key_value=" not in result.stdout + result.stderr


def test_hermes_diagnostic_is_static_read_only():
    content = SCRIPT.read_text(encoding="utf-8")
    assert "docker logs" not in content
    assert "docker exec" not in content
    assert "Config.Env" in content  # explicit prohibition in header, never as a template
    assert "--format '{{range .Config.Env}}" not in content
    assert "--check" in content
