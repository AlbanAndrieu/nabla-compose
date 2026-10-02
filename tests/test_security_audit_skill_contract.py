"""Contracts for the vendored defensive security-audit skill and report."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents" / "skills" / "security-audit"
AUDIT = ROOT / "docs" / "security-audits" / "2026-10-01-nabla-compose"
STORAGE = ROOT / "scripts" / "truenas" / "bootstrap-repository-storage.sh"


def test_security_audit_skill_is_vendored_with_provenance() -> None:
    required = {
        "SKILL.md",
        "RECONNAISSANCE.md",
        "HUNTING.md",
        "ATTACK-CLASSES.md",
        "VALIDATION-AND-REPORTING.md",
        "report-schema.json",
        "validate-findings.cjs",
        "validate-coverage-ledger.cjs",
        "LICENSE",
        "UPSTREAM.md",
    }
    assert required.issubset({path.name for path in SKILL.iterdir()})

    upstream = (SKILL / "UPSTREAM.md").read_text(encoding="utf-8")
    assert "cloudflare/security-audit-skill" in upstream
    assert "c1c8a8c1471069fb0e188eeaff69b8e8db6564a8" in upstream


def test_one_shot_audit_matches_cloudflare_full_audit_artifact_contract() -> None:
    required = {
        "run-metadata.json",
        "architecture.md",
        "coverage-ledger.json",
        "findings.json",
        "REPORT.md",
        "FINDINGS-DETAIL.md",
        "NEEDS-VALIDATION.md",
    }
    assert required.issubset({path.name for path in AUDIT.iterdir()})

    findings = json.loads((AUDIT / "findings.json").read_text(encoding="utf-8"))
    assert len(findings) == 1
    assert findings[0]["verdict"] == "needs_validation"
    assert findings[0]["fingerprint"] == "scanopy-daemon-public-bootstrap-boundary"

    metadata = json.loads((AUDIT / "run-metadata.json").read_text(encoding="utf-8"))
    assert metadata["profile"] == "quick"
    assert metadata["run_status"] == "incomplete"
    assert metadata["execution_policy"] == "sandboxed-source-and-local-only"

    ledger = json.loads((AUDIT / "coverage-ledger.json").read_text(encoding="utf-8"))
    assert len(ledger) == 5
    assert {unit["status"] for unit in ledger} <= {"covered", "candidate"}

    report = (AUDIT / "REPORT.md").read_text(encoding="utf-8")
    assert "No confirmed vulnerabilities" in report
    assert "INCOMPLETE / partial source review" in report
    assert "docker-socket-proxy" in report


def test_dsomm_dataset_is_explicit_repository_storage() -> None:
    script = STORAGE.read_text(encoding="utf-8")
    assert 'declared_paths["dsomm"]="APPS"' in script
    assert '"${APP_FILTER}" == "dsomm"' in script
