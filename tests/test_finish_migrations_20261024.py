"""Offline operator acceptance for the temporary TrueNAS migration runner.

All dependencies are fake, local commands; no TrueNAS API, keys, network or CI.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/truenas/finish-migrations-20261024.sh"
HASH = "a" * 64
ACK_RESTART = "I_ACCEPT_SEQUENTIAL_TRUENAS_RESTART"
ACK_MIGRATION = "I_ACCEPT_REVIEWED_RUNTIME_MIGRATION"


@pytest.fixture
def fake_operator(tmp_path):
    root = tmp_path / "repo"
    truenas = root / "scripts/truenas"
    truenas.mkdir(parents=True)
    target = truenas / SOURCE.name
    shutil.copyfile(SOURCE, target)
    binary = tmp_path / "bin"
    binary.mkdir()
    midclt = binary / "midclt"
    midclt.write_text("#!/bin/sh\nprintf '[]\\n'\n", encoding="utf-8")
    midclt.chmod(0o755)
    planner = truenas / "restart-catalog-v2-apps.py"
    planner.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "wave = 'gatus' if '--include-gatus' in args else "
        "'deferred' if '--include-deferred' in args else 'core'\n"
        "if '--apply' in args:\n"
        "    Path(os.environ['MUTATION_MARKER']).write_text('APPLIED:' + wave)\n"
        "else:\n"
        "    output = Path(args[args.index('--output')+1])\n"
        "    output.write_text(json.dumps({"
        "'inventorySource':'live-midclt', 'runtimeSecretsSource':'live-filesystem',"
        "'selectedWave':wave, 'selectedWaveReady':True,"
        "'planHash':'" + HASH + "'}))\n",
        encoding="utf-8",
    )
    for name in (
        "diagnose-gatus.sh", "diagnose-sentry.sh", "diagnose-defectdojo.sh",
        "diagnose-cyberbro.sh", "diagnose-prometheus-targets.sh",
        "triage-post-reboot-apps.sh",
    ):
        (truenas / name).write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    (truenas / "deploy-gatus.sh").write_text(
        "#!/bin/bash\n"
        "if [[ \"$1\" == --check ]]; then\n"
        "  [[ \"${MOCK_DRIFT:-false}\" != true ]]\n"
        "else\n"
        "  printf migrated >\"${MUTATION_MARKER}\"\n"
        "fi\n", encoding="utf-8",
    )
    report = tmp_path / "private"
    marker = tmp_path / "applied"
    env = os.environ | {
        "PATH": f"{binary}:{os.environ['PATH']}",
        "NABLA_MIGRATION_REPORT_ROOT": str(report),
        "MUTATION_MARKER": str(marker),
    }
    return target, env, report, marker


def invoke(fake_operator, *args, env_overrides=None):
    target, env, _, _ = fake_operator
    return subprocess.run(
        ["bash", str(target), *args],
        env=env | (env_overrides or {}),
        text=True, capture_output=True, check=False,
    )


def test_shell_parses_and_help_needs_no_truenas(fake_operator):
    target, _, _, marker = fake_operator
    assert subprocess.run(["bash", "-n", str(target)], check=False).returncode == 0
    result = invoke(fake_operator, "--help")
    assert result.returncode == 0
    assert "--plan-wave" in result.stdout
    assert not marker.exists()


@pytest.mark.parametrize("args", [
    ("--apply-wave", "core"),
    ("--apply-wave", "core", "--expected-plan-hash", "bad"),
    ("--apply-wave", "core", "--expected-plan-hash", HASH,
     "--acknowledge", "WRONG"),
    ("--apply-step", "gatus-config"),
    ("--apply-csi-smoke",),
    ("--plan-wave", "unknown"),
    ("--apply-step", "unknown", "--acknowledge", ACK_MIGRATION),
    ("--check", "--section", "unrecognized"),
])
def test_no_unapproved_mutations(fake_operator, args):
    _, _, _, marker = fake_operator
    result = invoke(fake_operator, *args)
    assert result.returncode != 0
    assert not marker.exists()


def test_plan_is_live_metadata_only_and_private(fake_operator):
    _, _, report, marker = fake_operator
    result = invoke(fake_operator, "--plan-wave", "gatus")
    assert result.returncode == 0, result.stdout + result.stderr
    assert HASH in result.stdout
    assert marker.exists() is False
    session, = list(report.glob("session-*"))
    assert session.stat().st_mode & 0o077 == 0
    plan, = list(session.glob("catalog-gatus.json"))
    assert plan.stat().st_mode & 0o077 == 0


@pytest.mark.skipif(os.geteuid() != 0, reason="TrueNAS apply requires root")
def test_apply_rejects_stale_hash_without_mutation(fake_operator):
    _, _, _, marker = fake_operator
    result = invoke(fake_operator, "--apply-wave", "core",
                    "--expected-plan-hash", "b" * 64,
                    "--acknowledge", ACK_RESTART)
    assert result.returncode == 1
    assert "plan drift" in result.stderr
    assert not marker.exists()


@pytest.mark.skipif(os.geteuid() != 0, reason="TrueNAS apply requires root")
def test_apply_delegates_verified_wave_then_runs_health_checks(fake_operator):
    _, _, _, marker = fake_operator
    result = invoke(fake_operator, "--apply-wave", "deferred",
                    "--expected-plan-hash", HASH, "--acknowledge", ACK_RESTART)
    assert result.returncode == 0, result.stdout + result.stderr
    assert marker.read_text() == "APPLIED:deferred"
    assert "apply-deferred" in result.stdout
    assert "prometheus" in result.stdout


@pytest.mark.skipif(os.geteuid() != 0, reason="TrueNAS apply requires root")
def test_remediation_drift_requires_two_explicit_controls(fake_operator):
    _, _, _, marker = fake_operator
    options = ("--apply-step", "gatus-config", "--acknowledge", ACK_MIGRATION)
    denied = invoke(fake_operator, *options, env_overrides={"MOCK_DRIFT": "true"})
    assert denied.returncode == 1
    assert not marker.exists()
    approved = invoke(fake_operator, *options, "--allow-reviewed-drift",
                      env_overrides={"MOCK_DRIFT": "true"})
    assert approved.returncode == 0, approved.stdout + approved.stderr
    assert marker.read_text() == "migrated"
    assert "WARN=1" in approved.stdout


def test_missing_github_or_ssh_environment_not_required_for_plan(fake_operator):
    result = invoke(fake_operator, "--plan-wave", "core")
    assert result.returncode == 0
    assert "selectedWaveReady=true" in result.stdout
