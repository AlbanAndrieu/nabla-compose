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
SECTIONS = SOURCE.with_name("migration-diagnostic-sections.sh")
OPERATOR = SOURCE.with_name("migration-operator.sh")
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
    shutil.copyfile(SECTIONS, truenas / SECTIONS.name)
    shutil.copyfile(OPERATOR, truenas / OPERATOR.name)
    # Fake the terminal interface used by the production runner. No TrueNAS.
    lib = root / "scripts/lib/diagnostic-ui.sh"
    lib.parent.mkdir(parents=True, exist_ok=True)
    lib.write_text(
        "diag_ui_init() { return 0; }\n"
        "diag_ok() { printf 'OK: %s\\n' \"$*\"; }\n"
        "diag_warn() { printf 'WARN: %s\\n' \"$*\"; }\n"
        "diag_fail() { printf 'FAIL: %s\\n' \"$*\"; }\n"
        "diag_info() { printf 'INFO: %s\\n' \"$*\"; }\n"
        "diag_section() { printf 'SECTION: %s\\n' \"$*\"; }\n",
        encoding="utf-8",
    )
    # Operator commands are a tracked, non-executable runbook.
    runbook = root / "docs/runbooks/2026-10-24-homelab-operator-next-commands.md"
    runbook.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE.parents[2] / "docs/runbooks" / runbook.name, runbook)
    canonical = root / "docs/runbooks/truenas-migration-operator.md"
    shutil.copyfile(
        SOURCE.parents[2] / "docs/runbooks" / canonical.name, canonical,
    )
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
        "'selectedWave':wave,"
        "'selectedWaveReady':os.getenv('MOCK_WAVE_BLOCKED') != '1',"
        "'selectedWaveBlocker':'PRIVATE_TOKEN_MUST_NOT_PRINT',"
        "'planHash':'" + HASH + "'}))\n",
        encoding="utf-8",
    )
    # A successful mock wave must be followed by a successful health check.
    (truenas / "diagnose-service-readiness.py").write_text(
        "raise SystemExit(0)\n", encoding="utf-8",
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


def test_stable_migration_operator_delegates_without_runtime_probing(fake_operator):
    target, env, report, marker = fake_operator
    wrapper = target.with_name(OPERATOR.name)
    assert subprocess.run(["bash", "-n", str(wrapper)], check=False).returncode == 0
    result = subprocess.run(
        ["bash", str(wrapper), "--help"], env=env,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--plan-wave" in result.stdout
    assert not report.exists()
    assert not marker.exists()


def test_stable_operator_rejects_missing_legacy_target(fake_operator):
    target, env, report, marker = fake_operator
    wrapper = target.with_name(OPERATOR.name)
    target.unlink()
    result = subprocess.run(
        ["bash", str(wrapper), "--check"], env=env,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "canonical migration operator unavailable" in result.stderr
    assert not report.exists()
    assert not marker.exists()


def test_readonly_registry_is_required_and_rejects_symlinks(fake_operator):
    target, _, report, marker = fake_operator
    registry = target.with_name("migration-diagnostic-sections.sh")
    original = registry.read_bytes()
    registry.unlink()
    missing = invoke(fake_operator, "--check", "--section", "critical")
    assert missing.returncode == 2
    assert "read-only diagnostic registry missing or symlinked" in missing.stderr
    assert not marker.exists()
    assert not report.exists()
    registry.symlink_to(target.with_name("diagnose-gatus.sh"))
    linked = invoke(fake_operator, "--check", "--section", "critical")
    assert linked.returncode == 2
    assert "read-only diagnostic registry missing or symlinked" in linked.stderr
    assert not marker.exists()
    registry.unlink()
    registry.write_bytes(original)


def test_readonly_registry_parses_and_preserves_guarded_apply_surface():
    caller = SOURCE.read_text(encoding="utf-8")
    module = SECTIONS.read_text(encoding="utf-8")
    assert subprocess.run(["bash", "-n", str(SECTIONS)], check=False).returncode == 0
    assert 'source "${READONLY_REGISTRY}"' in caller
    assert caller.index("Apply denied: only the canonical") < caller.index(
        'source "${READONLY_REGISTRY}"'
    )
    assert '    critical)' in module
    assert 'for service in prometheus openrag sentry akvorado defectdojo; do' in module
    assert "check_section()" not in caller
    for forbidden in ("--apply", "docker restart", "midclt call app.", "zfs destroy"):
        assert forbidden not in module


def test_next_commands_print_only_runbook_location_without_runtime_access(fake_operator):
    _, _, report, marker = fake_operator
    result = invoke(fake_operator, "--next-commands")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == (
        "RUNBOOK=docs/runbooks/truenas-migration-operator.md\n"
    )
    assert "NEVER-LOG" not in result.stdout
    assert len(result.stdout) < 100
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


@pytest.mark.parametrize("args", [
    ("--apply-step", "gatus-config", "--check", "--acknowledge", ACK_MIGRATION),
    ("--check", "--apply-step", "gatus-config", "--acknowledge", ACK_MIGRATION),
    ("--plan-wave", "core", "--apply-wave", "core",
     "--expected-plan-hash", HASH, "--acknowledge", ACK_RESTART),
    ("--apply-wave", "core", "--check",
     "--expected-plan-hash", HASH, "--acknowledge", ACK_RESTART),
    ("--apply-csi-smoke", "--check", "--acknowledge", ACK_MIGRATION),
    ("--local-gates", "--check"),
    ("--next-commands", "--plan-wave", "core"),
    ("--check", "--check"),
])
def test_mixed_execution_modes_are_rejected_before_runtime(fake_operator, args):
    _, _, report, marker = fake_operator
    result = invoke(fake_operator, *args)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "choose exactly one execution mode" in result.stderr
    assert not marker.exists()
    assert not report.exists()


def test_planner_blocker_is_not_printed_from_private_json(fake_operator):
    _, _, report, marker = fake_operator
    result = invoke(
        fake_operator, "--plan-wave", "core",
        env_overrides={"MOCK_WAVE_BLOCKED": "1"},
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "wave not ready; inspect the private plan report" in result.stdout
    assert "PRIVATE_TOKEN_MUST_NOT_PRINT" not in result.stdout + result.stderr
    assert not marker.exists()
    assert len(list(report.glob("session-*"))) == 1


def test_new_read_only_sections_are_documented():
    script = SECTIONS.read_text(encoding="utf-8")
    for section in (
        "observability", "prometheus", "openrag", "akvorado",
        "secrets", "convergence", "lan",
    ):
        assert f"    {section})" in script
    assert f" --check --section {section}" in (
        SOURCE.parents[2]
        / "docs/runbooks/2026-10-24-homelab-operator-next-commands.md"
    ).read_text(encoding="utf-8")
    assert "--require-inserts --observe-seconds" in script
    assert "verify-fastapi-lan-probes.sh" in script


def test_postmigration_diagnostics_are_explicit_and_read_only(fake_operator):
    _, _, report, marker = fake_operator
    lib = SECTIONS.read_text(encoding="utf-8")
    runner = SOURCE.read_text(encoding="utf-8")
    assert "    postmigration)" in lib
    for name in (
        "postmigration-catalog",
        "postmigration-service-readiness",
        "postmigration-gatus",
        "postmigration-prometheus",
    ):
        assert name in lib
    assert "postmigration" not in runner.split("for part in ", 1)[1].split("; do", 1)[0]
    result = invoke(fake_operator, "--check", "--section", "postmigration")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Invalid section" not in result.stderr
    assert not marker.exists()
    assert len(list(report.glob("session-*"))) == 1


def test_apisix_is_optional_until_deployed(fake_operator):
    _, _, report, marker = fake_operator
    lib = SECTIONS.read_text(encoding="utf-8")
    assert "    apisix)" in lib
    assert "record apisix-runtime SKIP" in lib
    result = invoke(fake_operator, "--check", "--section", "apisix")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "SKIP=1" in result.stdout
    assert not marker.exists()
    assert len(list(report.glob("session-*"))) == 1


def test_critical_read_only_section_combines_five_independent_gates(
    fake_operator,
):
    """Missing synthetic check tools are reported without aborting the others."""
    target, _, report, marker = fake_operator
    source = SOURCE.read_text(encoding="utf-8") + SECTIONS.read_text(encoding="utf-8")
    assert 'all|platform|migrations|catalog|services|ai|critical|prometheus|openrag|sentry|akvorado|defectdojo' in source
    assert 'for service in prometheus openrag sentry akvorado defectdojo; do' in source
    assert 'run_check sentry-consumers bash scripts/truenas/diagnose-sentry-consumers.sh --check' in source
    result = invoke(fake_operator, "--check", "--section", "critical")
    # Missing fixture-specific read-only probes cause a controlled FAIL,
    # not "Invalid section" and never a mutation.
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Invalid section" not in result.stderr
    assert not marker.exists()
    sessions = list(report.glob("session-*"))
    assert len(sessions) == 1
    names = {path.name for path in sessions[0].glob("*.log")}
    for expected in (
        "prometheus-targets.log",
        "openrag-dependencies.log",
        "sentry-consumers.log",
        "akvorado-blocked.log",
        "akvorado-fresh-inserts.log",
        "defectdojo-preflight.log",
        "defectdojo-private-ingress.log",
    ):
        assert expected in names


def test_legacy_openrag_secret_apply_is_rejected(fake_operator):
    """Legacy OpenRAG secret source must not be a mutable migration step."""
    result = invoke(
        fake_operator, "--apply-step", "openrag-secret",
        "--acknowledge", ACK_MIGRATION,
    )
    assert result.returncode == 2
    assert "Invalid migration step" in result.stderr
    script = SOURCE.read_text(encoding="utf-8")
    assert 'openrag-secret) SCRIPT=' not in script


def test_operator_runbook_mentions_merged_site_and_api_prs(fake_operator):
    runbook = (
        SOURCE.parents[2]
        / "docs/runbooks/2026-10-24-homelab-operator-next-commands.md"
    ).read_text(encoding="utf-8")
    assert "PR site #254 et FastAPI" in runbook
    assert "ont été fusionnées" in runbook
    assert "--check --section prometheus" in runbook
    assert "--check --section openrag" in runbook
    assert "--check --section akvorado" in runbook
    assert "Ne pas lancer l'ancien reconciler en" in runbook


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


def test_local_gate_mode_and_sentry_section_contract():
    source = SOURCE.read_text(encoding="utf-8") + SECTIONS.read_text(encoding="utf-8")
    assert '--local-gates) ACTION="local-gates"' in source
    assert '(( EUID != 0 ))' in source
    assert ("run_check sentry-consumers bash "
            "scripts/truenas/diagnose-sentry-consumers.sh --check") in source
    assert ("run_check sentry-recovery-preflight bash "
            "scripts/truenas/recover-sentry-deploying.sh --check") in source
    assert 'case "${SECTION}" in' in source
    assert "|sentry|" in source
    assert "for part in platform migrations catalog services ai sentry" in source


def test_local_gates_reject_mixed_mutation_flags(fake_operator):
    for args in (
        ("--local-gates", "--apply-step", "sentry-system"),
        ("--local-gates", "--section", "sentry"),
        ("--local-gates", "--acknowledge", ACK_MIGRATION),
    ):
        assert invoke(fake_operator, *args).returncode != 0


@pytest.mark.skipif(os.geteuid() == 0, reason="local gate requires non-root")
@pytest.mark.parametrize("failing,expected", [
    ("", 5),
    ("catalog-convergence-check", 3),
])
def test_local_gates_run_in_order_and_fail_closed(
    fake_operator, tmp_path, noexec_safe_bash_mocks, failing, expected
):
    _, base_env, report, marker = fake_operator
    fake_just = tmp_path / "bin" / "just"
    fake_just.write_text(chr(10).join((
        "#!/usr/bin/env bash",
        'echo "$1" >> "$MOCK_GATE_LOG"',
        '[[ "$1" != "$MOCK_GATE_FAIL" ]]',
        "",
    )), encoding="utf-8")
    fake_just.chmod(0o600)
    log = tmp_path / "gate-calls"
    env = dict(base_env)
    env["MOCK_GATE_LOG"] = str(log)
    env["MOCK_GATE_FAIL"] = failing
    env = noexec_safe_bash_mocks(env, "just")
    result = invoke(fake_operator, "--local-gates", env_overrides=env)
    expected_order = [
        "migration-20261024-commands",
        "migration-20261024-test",
        "catalog-convergence-check",
        "agent-skills-check",
        "quality",
    ]
    assert log.read_text(encoding="utf-8").splitlines() == expected_order[:expected]
    assert result.returncode == (1 if failing else 0)
    assert not marker.exists()
    assert not report.exists()


def test_full_quality_recipe_invokes_same_canonical_gate_without_mise():
    """TrueNAS local gate must not auto-install the mise.lock tool matrix."""
    root = SOURCE.parents[2]
    justfile = (root / "justfile").read_text(encoding="utf-8")
    assert "\nquality:\n    bash scripts/agent-quality-gate.sh\n" in justfile
    assert "migration-20261024-local-gates:" in justfile
    assert "bash scripts/truenas/finish-migrations-20261024.sh --local-gates" in justfile
    assert (root / "scripts/agent-quality-gate.sh").is_file()


def test_roadmap_critical_policy_not_removed_by_migration_consolidation():
    """Current roadmap must link to preserved historical policy and evidence."""
    root = SOURCE.parents[2]
    roadmap = (root / "docs/roadmap.md").read_text(encoding="utf-8")
    archive = (root / "docs/archive/roadmap-through-2026-10-24.md").read_text(
        encoding="utf-8"
    )
    heading = (
        "## P0 — Agent skill precedence and Compose/FastAPI/Site "
        "convergence (2026-10-24)"
    )
    assert heading in archive
    assert len(archive.splitlines()) > 3000
    assert len(roadmap.splitlines()) < 300
    assert "archive/roadmap-through-2026-10-24.md" in roadmap
    for marker in ("Ask the user", "democratic-csi", "catalogRevision", "entityRef"):
        assert marker in archive
        assert marker in roadmap


def test_mise_lock_is_not_rewritten_by_local_quality_runner():
    """The tracked lock remains version 2; do not regenerate it on TrueNAS."""
    lockfile = (SOURCE.parents[2] / "mise.lock").read_text(encoding="utf-8")
    assert "lockfile_version = 2" in lockfile
    runner = SOURCE.read_text(encoding="utf-8")
    assert "mise lock" not in runner
    assert "mise install" not in runner
