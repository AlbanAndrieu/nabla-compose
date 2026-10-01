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


def test_one_shot_audit_keeps_unverified_leads_unconfirmed() -> None:
    findings = json.loads((AUDIT / "findings.json").read_text(encoding="utf-8"))
    assert findings
    assert {entry["verdict"] for entry in findings} == {"needs_validation"}

    report = (AUDIT / "REPORT.md").read_text(encoding="utf-8")
    assert "Aucune vulnérabilité n'est marquée **confirmed**" in report
    assert "docker-socket-proxy" in report
    assert "--api.insecure=true" in report


def test_dsomm_dataset_is_explicit_repository_storage() -> None:
    script = STORAGE.read_text(encoding="utf-8")
    assert 'declared_paths["dsomm"]="APPS"' in script
    assert '"${APP_FILTER}" == "dsomm"' in script
