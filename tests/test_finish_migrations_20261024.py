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
    # Operator commands are a tracked, non-executable runbook.
    runbook = root / "docs/runbooks/2026-10-24-homelab-operator-next-commands.md"
    runbook.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE.parents[2] / "docs/runbooks" / runbook.name, runbook)
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
        "  [[ \"${MOCK_DRIFT:-false}\" != true || -f \"${MUTATION_MARKER}\" ]]\n"
        "else\n"
        "  printf migrated >\"${MUTATION_MARKER}\"\n"
        "fi\n", encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q", "-b", "master"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "ci@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Local Operator Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-qm", "synthetic fixture"],
                   cwd=root, check=True)
    report = tmp_path / "private"
    marker = tmp_path / "applied"
    env = os.environ | {
        "PATH": f"{binary}:{os.environ['PATH']}",
        "NABLA_MIGRATION_REPORT_ROOT": str(report),
        "MUTATION_MARKER": str(marker),
        "NABLA_MIGRATION_CANONICAL_ROOT": str(root),
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


def test_next_commands_print_runbook_without_runtime_access(fake_operator):
    _, _, report, marker = fake_operator
    result = invoke(fake_operator, "--next-commands")
    assert result.returncode == 0, result.stdout + result.stderr
    for name in ("Akvorado", "Prometheus", "OpenRAG", "Vaultwarden", "Talos"):
        assert name in result.stdout
    assert "NEVER-LOG" not in result.stdout
    assert not marker.exists()
    assert not report.exists()


@pytest.mark.parametrize("args", [
    ("--next-commands", "--apply-step", "openrag-secret"),
    ("--next-commands", "--section", "secrets"),
    ("--next-commands", "--acknowledge", ACK_MIGRATION),
])
def test_next_commands_rejects_mixed_apply_flags(fake_operator, args):
    _, _, report, marker = fake_operator
    result = invoke(fake_operator, *args)
    assert result.returncode != 0
    assert not marker.exists()
    assert not report.exists()


def test_new_read_only_sections_are_documented():
    script = SOURCE.read_text(encoding="utf-8")
    for section in ("observability", "secrets", "convergence", "lan"):
        assert f"    {section})" in script
    assert f" --check --section {section}" in (
        SOURCE.parents[2]
        / "docs/runbooks/2026-10-24-homelab-operator-next-commands.md"
    ).read_text(encoding="utf-8")
    assert "--require-inserts --observe-seconds" in script
    assert "verify-fastapi-lan-probes.sh" in script


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


@pytest.mark.skipif(os.geteuid() != 0, reason="TrueNAS apply requires root")
def test_apply_forbidden_from_noncanonical_worktree(fake_operator, tmp_path):
    _, _, _, marker = fake_operator
    result = invoke(fake_operator, "--apply-wave", "core",
                    "--expected-plan-hash", HASH,
                    "--acknowledge", ACK_RESTART,
                    env_overrides={
                        "NABLA_MIGRATION_CANONICAL_ROOT": str(tmp_path),
                    })
    assert result.returncode == 2
    assert "canonical TrueNAS checkout" in result.stderr
    assert not marker.exists()


@pytest.mark.skipif(os.geteuid() != 0, reason="TrueNAS apply requires root")
def test_apply_forbidden_on_dirty_canonical_checkout(fake_operator):
    target, _, _, marker = fake_operator
    (target.parent.parent.parent / "dirty-file").write_text("not committed")
    result = invoke(fake_operator, "--apply-wave", "core",
                    "--expected-plan-hash", HASH,
                    "--acknowledge", ACK_RESTART)
    assert result.returncode == 2
    assert "superproject is dirty" in result.stderr
    assert not marker.exists()


@pytest.mark.skipif(os.geteuid() != 0, reason="TrueNAS apply requires root")
def test_apply_forbidden_on_unreviewed_feature_branch(fake_operator):
    target, _, _, marker = fake_operator
    subprocess.run(["git", "switch", "-qc", "feature/unreviewed"],
                   cwd=target.parent.parent.parent, check=True)
    result = invoke(fake_operator, "--apply-wave", "core",
                    "--expected-plan-hash", HASH,
                    "--acknowledge", ACK_RESTART)
    assert result.returncode == 2
    assert "never a Draft PR/worktree" in result.stderr
    assert not marker.exists()
