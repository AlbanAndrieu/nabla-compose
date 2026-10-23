"""Offline regression checks for scoped Prometheus config repair.

No containers, ZFS datasets or privileged filesystem mutations are touched.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/repair-prometheus-config-access.sh"


def sandbox(tmp_path: Path, *, runtime_user: str = "568:568",
            mount_ok: bool = True, symlink: bool = False,
            noexec_safe_bash_mocks=None):
    root = tmp_path / "repo"
    script_dir = root / "scripts" / "truenas"
    script_dir.mkdir(parents=True)
    script = script_dir / SCRIPT.name
    shutil.copyfile(SCRIPT, script)
    config_dir = root / "apps" / "prometheus"
    config_dir.mkdir(parents=True)
    config = config_dir / "prometheus.yml"
    if symlink:
        private = tmp_path / "private.yml"
        private.write_text("SECRET=DONT_PRINT\n", encoding="utf-8")
        config.symlink_to(private)
    else:
        config.write_text("global:\n  scrape_interval: 15s\n",
                          encoding="utf-8")
        config.chmod(0o600)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$*\" == *'{{.Config.User}}'* ]]; then\n"
        "  printf '%s\\n' \"$TEST_RUNTIME_USER\"\n"
        "elif [[ \"$*\" == *'/etc/prometheus'* ]]; then\n"
        "  printf '%s\\n' \"$TEST_MOUNT\"\n"
        "else exit 99; fi\n",
        encoding="utf-8"
    )
    docker.chmod(0o755)
    getent = fake_bin / "getent"
    getent.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1\" == group && \"$2\" == apps ]]; then\n"
        "  echo 'apps:x:568:'\n"
        "else exit 2; fi\n",
        encoding="utf-8"
    )
    getent.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "PATH": str(fake_bin) + os.pathsep + env["PATH"],
        "TEST_RUNTIME_USER": runtime_user,
        "TEST_MOUNT": str(config_dir if mount_ok else tmp_path / "foreign"),
    })
    if noexec_safe_bash_mocks is not None:
        env = noexec_safe_bash_mocks(env, "docker", "getent")
    return script, config, env


@pytest.mark.parametrize("runtime_user,mount_ok,symlink,reason", [
    ("568:568", True, False, "config group mismatch"),
    ("999:999", True, False, "runtime user differs"),
    ("568:568", False, False, "mount differs"),
    ("568:568", True, True, "unsafe prometheus.yml"),
])
def test_repair_preflight_fails_closed(
    tmp_path, runtime_user, mount_ok, symlink, reason,
    noexec_safe_bash_mocks
):
    script, config, env = sandbox(
        tmp_path, runtime_user=runtime_user, mount_ok=mount_ok,
        symlink=symlink, noexec_safe_bash_mocks=noexec_safe_bash_mocks
    )
    before = config.lstat().st_mode
    result = subprocess.run(
        ["bash", str(script), "--check"], capture_output=True,
        text=True, env=env, check=False, timeout=10
    )
    assert result.returncode == 1
    assert reason in result.stderr
    assert config.lstat().st_mode == before
    assert "SECRET=DONT_PRINT" not in result.stdout + result.stderr


def test_repair_is_explicit_and_file_scoped() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], check=False, capture_output=True,
        text=True
    )
    assert result.returncode == 0, result.stderr
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'MODE="${1:---check}"' in source
    assert 'EUID == 0' in source
    assert 'chmod 0640 -- "${CONFIG}"' in source
    assert 'chgrp -- "${EXPECTED_GID}" "${CONFIG}"' in source
    assert 'eq .Destination "/etc/prometheus"' in source
    assert '/mnt/cpool/prometheus/data' in source  # informational only
    for forbidden in ("docker restart", "app.redeploy", "app.start",
                      "rm -rf", "chmod -R", "sqlite3", "truncate "):
        assert forbidden not in source


def test_apply_without_root_never_modifies_prometheus_config(tmp_path):
    """Even a matching Docker bind cannot authorize mutation without sudo."""
    if os.geteuid() == 0:
        pytest.skip("root-only runner: cannot validate non-root safety")
    script, config, env = sandbox(tmp_path)
    before = (config.stat().st_uid, config.stat().st_gid,
              config.stat().st_mode, config.read_bytes())
    result = subprocess.run(
        ["bash", str(script), "--apply"],
        capture_output=True, text=True, env=env, check=False, timeout=10
    )
    after = (config.stat().st_uid, config.stat().st_gid,
             config.stat().st_mode, config.read_bytes())
    assert result.returncode == 1
    assert "--apply requires sudo" in result.stderr
    assert before == after
