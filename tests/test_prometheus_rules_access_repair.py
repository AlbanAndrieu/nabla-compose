"""Offline contract for scoped Prometheus rule repair; no live TrueNAS access."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/truenas/repair-prometheus-rules-access.sh"


def fixture(tmp_path, noexec_safe_bash_mocks, *, deny):
    script_path = tmp_path / "repo/scripts/truenas/repair-prometheus-rules-access.sh"
    script_path.parent.mkdir(parents=True)
    source = SOURCE.read_text(encoding="utf-8")
    guard = "(( EUID == 0 )) || fail 'sudo is required for effective identity tests'"
    assert source.count(guard) == 1
    # Only the synthetic test copy bypasses root to exercise --check as a CI user.
    script_path.write_text(source.replace(guard, ": # TEST_ONLY"), encoding="utf-8")
    rule_dir = tmp_path / "repo/apps/prometheus/rules"
    rule_dir.mkdir(parents=True)
    files = []
    for name in ("good.rules.yml", "denied-one.rules.yml", "denied-two.rules.yml"):
        f = rule_dir / name
        f.write_text("groups: []", encoding="utf-8")
        f.chmod(0o600)
        files.append(f)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    stubs = {
        "docker": chr(10).join((
            "#!/usr/bin/env bash",
            'if [[ "$*" == *"{{.Config.User}}"* ]]; then echo "568:568";',
            'elif [[ "$*" == *"/etc/prometheus"* ]]; then echo "$MOCK_MOUNT";',
            "else exit 99; fi",
            "",
        )),
        "getent": "#!/usr/bin/env bash" + chr(10) + "echo 'apps:x:568:'" + chr(10),
        "setpriv": chr(10).join((
            "#!/usr/bin/env bash",
            'if [[ "$MOCK_DENY" == yes && "${@: -1}" == *"/denied-"* ]]; then exit 1; fi',
            "exit 0",
            "",
        )),
    }
    for name, contents in stubs.items():
        file = binaries / name
        file.write_text(contents, encoding="utf-8")
        file.chmod(0o600)
    env = dict(os.environ)
    env["PATH"] = str(binaries) + os.pathsep + env["PATH"]
    env["MOCK_MOUNT"] = str(rule_dir.parent)
    env["MOCK_DENY"] = "yes" if deny else "no"
    return script_path, noexec_safe_bash_mocks(
        env, "docker", "getent", "setpriv"
    ), files


@pytest.mark.parametrize("deny,status,count", [
    (True, 1, "unreadable=2"),
    (False, 0, "unreadable=0"),
])
def test_read_only_counts_and_no_file_mutation(
    tmp_path, noexec_safe_bash_mocks, deny, status, count
):
    script, env, files = fixture(tmp_path, noexec_safe_bash_mocks, deny=deny)
    before = [(p.stat().st_mode, p.read_bytes()) for p in files]
    result = subprocess.run(
        ["bash", str(script), "--check"], capture_output=True,
        text=True, check=False, env=env, timeout=12
    )
    assert result.returncode == status, result.stdout + result.stderr
    assert count in result.stdout
    assert "rules_total=3" in result.stdout
    assert before == [(p.stat().st_mode, p.read_bytes()) for p in files]
    assert "denied-one.rules.yml" not in result.stdout + result.stderr


def test_apply_requires_exact_operator_ack_and_count(
    tmp_path, noexec_safe_bash_mocks
):
    script, env, files = fixture(tmp_path, noexec_safe_bash_mocks, deny=True)
    initial = [p.read_bytes() for p in files]
    for args in (
        ("--apply",),
        ("--apply", "--expected-unreadable", "2"),
        ("--apply", "--expected-unreadable", "0",
         "--acknowledge", "I_ACCEPT_PROMETHEUS_RULES_PERMISSION_REPAIR"),
    ):
        result = subprocess.run(
            ["bash", str(script), *args], env=env,
            capture_output=True, text=True, check=False, timeout=12
        )
        assert result.returncode != 0
        assert initial == [p.read_bytes() for p in files]


def test_production_script_is_file_scoped():
    check = subprocess.run(
        ["bash", "-n", str(SOURCE)], capture_output=True,
        text=True, check=False
    )
    assert check.returncode == 0, check.stderr
    source = SOURCE.read_text(encoding="utf-8")
    assert "I_ACCEPT_PROMETHEUS_RULES_PERMISSION_REPAIR" in source
    assert "setpriv --reuid 568 --regid 568 --clear-groups" in source
    assert "chgrp -- 568" in source
    assert "chmod 0640" in source
    for forbidden in (
        "docker restart", "docker start", "app.redeploy",
        "chmod -R", "chgrp -R", "rm -rf", "docker exec",
        "prometheus/data", "sqlite3",
    ):
        assert forbidden not in source
