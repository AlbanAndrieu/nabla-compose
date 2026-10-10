"""Contracts for dependency ordered homelab service diagnostic."""

import ast
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts/truenas/audit-homelab-service-dependencies.py"
WRAPPER = ROOT / "scripts/truenas/check-homelab-services.sh"


def test_dependency_audit_contract() -> None:
    ast.parse(AUDIT.read_text(encoding="utf-8"))
    source = AUDIT.read_text(encoding="utf-8")
    assert 'plan["start_waves"]' in source
    assert 'plan.get("required_edges"' in source
    assert "socket.create_connection" in source
    assert "urlopen(url" in source
    assert "NO_COLOR" in source
    assert "✅" in source
    assert "❌" in source


def test_wrapper_keeps_existing_checks() -> None:
    subprocess.run(["bash", "-n", str(WRAPPER)], check=True)
    source = WRAPPER.read_text(encoding="utf-8")
    assert "--deep" in source
    assert "plan-app-lifecycle-order.py" in source
    assert "audit-homelab-service-dependencies.py" in source
    assert "check-dsomm-post-reboot.py" in source
    assert "diagnose-fastapi-integrations.py" in source
    assert "audit-internal-routes.py" in source
    for forbidden in ("app.redeploy", "docker restart", "app.start"):
        assert forbidden not in source


def test_monitoring_coverage_not_equated_to_runtime_outage() -> None:
    source = AUDIT.read_text(encoding="utf-8")
    assert "probe_gaps={uncovered}" in source
    assert "missing host/port metadata\" not in detail" in source
    assert "Catalog mapping to complete:" in source
