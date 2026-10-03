"""Contracts for the vendored Cloudflare security-audit skill and audit artifacts."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents" / "skills" / "security-audit"
AUDIT_ROOT = ROOT / "docs" / "security-audits"
AUDIT = AUDIT_ROOT / "2026-10-01-cloudflare-security-audit"


def test_cloudflare_security_audit_skill_is_vendored_with_provenance() -> None:
    required = {
        "SKILL.md",
        "RECONNAISSANCE.md",
        "HUNTING.md",
        "VALIDATION-AND-REPORTING.md",
        "ATTACK-CLASSES.md",
        "CLOUD-AND-DEPLOYMENT.md",
        "SUPPLY-CHAIN-AND-RELEASE.md",
        "report-schema.json",
        "validate-findings.cjs",
        "validate-coverage-ledger.cjs",
        "LICENSE",
        "UPSTREAM.md",
    }
    assert required <= {path.name for path in SKILL.iterdir()}

    info = (SKILL / "UPSTREAM.md").read_text(encoding="utf-8")
    assert "cloudflare/security-audit-skill" in info
    assert "c1c8a8c1471069fb0e188eeaff69b8e8db6564a8" in info
    assert "License: MIT" in info
    assert "Vendored commit" in info


def test_agent_policy_routes_explicit_audits_to_vendored_skill() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "explicit security audit, vulnerability review or source-first pen-test" in agents
    assert "load `security-audit`" in agents
    assert "incomplete-run rules" in agents


def test_one_shot_audit_artifacts_are_self_describing_and_incomplete() -> None:
    expected = {
        "run-metadata.json",
        "architecture.md",
        "coverage-ledger.json",
        "findings.json",
        "REPORT.md",
        "FINDINGS-DETAIL.md",
        "NEEDS-VALIDATION.md",
    }
    assert expected <= {path.name for path in AUDIT.iterdir()}

    metadata = json.loads((AUDIT / "run-metadata.json").read_text(encoding="utf-8"))
    assert metadata["profile"] == "quick"
    assert metadata["source_ref"] == "4fa9eb8d262bab437c99773475fcf84e489be863"
    assert metadata["run_status"] == "incomplete"
    assert "independent" in metadata["incomplete_reason"]
    assert metadata["execution_policy"] == "sandboxed-source-and-local-only"

    findings = json.loads((AUDIT / "findings.json").read_text(encoding="utf-8"))
    assert any(
        finding.get("fingerprint") == "scanopy-daemon-public-bootstrap-boundary"
        and finding.get("verdict") == "needs_validation"
        for finding in findings
    )

    report = (AUDIT / "REPORT.md").read_text(encoding="utf-8")
    assert "partial" in report.lower()
    assert "no confirmed vulnerabilities" in report.lower()
    assert "Scanopy" in report


def test_precommit_routes_skill_changes_to_contract() -> None:
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert config.count("id: security-audit-skill-contract") == 1
    assert "tests/test_security_audit_skill_contract.py" in config
    assert "docs/security-audits/" in config


def test_all_committed_audit_json_passes_vendored_cloudflare_validators() -> None:
    node = shutil.which("node")
    assert node is not None, "node is required to validate committed security-audit artifacts"

    audit_dirs = sorted(
        path
        for path in AUDIT_ROOT.iterdir()
        if path.is_dir()
        and (path / "findings.json").is_file()
        and (path / "coverage-ledger.json").is_file()
    )
    assert audit_dirs, "at least one committed security audit is required"

    validators = (
        ("findings.json", SKILL / "validate-findings.cjs"),
        ("coverage-ledger.json", SKILL / "validate-coverage-ledger.cjs"),
    )
    for audit_dir in audit_dirs:
        for artifact_name, validator in validators:
            result = subprocess.run(
                [node, str(validator), str(audit_dir / artifact_name)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, (
                f"{audit_dir.name}/{artifact_name} failed Cloudflare validation:\n"
                f"{result.stdout}{result.stderr}"
            )
