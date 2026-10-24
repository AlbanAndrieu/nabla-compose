"""Offline bounded Akvorado orchestrator config mount checks."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-akvorado-config.sh"
CONFIG = ROOT / "apps/akvorado/config/akvorado.yaml"


@pytest.mark.parametrize("drift,expected_code,expected", [
    ("0", 0, "orchestrator_config_bind=MATCH"),
    ("1", 1, "orchestrator_config_bind=DRIFT"),
])
def test_akvorado_config_mount_attestation_is_read_only(
    tmp_path, noexec_safe_bash_mocks, drift, expected_code, expected
):
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    docker = fakebin / "docker"
    docker.write_text("\n".join([
        "#!/usr/bin/env bash",
        'case "$1" in',
        '  ps) if [[ "$*" == *"project=ix-akvorado"* ]]; then',
        '        echo aaaaaaaaaaaa; fi ;;',
        '  inspect) echo running ;;',
        '  exec) if [[ "$AKV_TEST_DRIFT" == 1 ]]; then',
        '          echo "0000000000000000000000000000000000000000000000000000000000000000  ignored";',
        '        else sha256sum "$AKV_TEST_CONFIG"; fi ;;',
        '  *) exit 99 ;;',
        'esac',
        "",
    ]), encoding="utf-8")
    docker.chmod(0o600)
    env = dict(os.environ)
    env.update({
        "PATH": str(fakebin) + os.pathsep + env["PATH"],
        "AKV_TEST_CONFIG": str(CONFIG),
        "AKV_TEST_DRIFT": drift,
    })
    env = noexec_safe_bash_mocks(env, "docker")
    result = subprocess.run(
        ["bash", str(SCRIPT), "--check"], env=env, capture_output=True,
        text=True, check=False, timeout=10
    )
    output = result.stdout + result.stderr
    assert result.returncode == expected_code, output
    assert expected in output
    assert "172.17.0.1" not in output
    assert "akvorado-flows" not in output


def test_akvorado_config_probe_refuses_mutation_flags():
    proc = subprocess.run(["bash", "-n", str(SCRIPT)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    text = SCRIPT.read_text(encoding="utf-8")
    for mutation in ("app.redeploy", "docker restart", "docker compose up",
                     "rm -rf", "chmod ", "chgrp "):
        assert mutation not in text
    bad = subprocess.run(["bash", str(SCRIPT), "--apply"],
                         capture_output=True, text=True, check=False)
    assert bad.returncode == 2
