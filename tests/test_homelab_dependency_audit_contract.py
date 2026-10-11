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


def test_docker_only_dns_requires_in_network_check() -> None:
    source = AUDIT.read_text(encoding="utf-8")
    assert '"kafka", "sentry-clickhouse"' in source
    assert "requires in-network probe" in source
    assert "uncovered += len(host_only)" in source


def test_portracker_monitor_matches_observed_published_port() -> None:
    import yaml

    compose = yaml.safe_load((ROOT / "apps/portracker/compose.yml").read_text())
    service = compose["services"]["portracker"]
    monitor = service["x-nabla"]["monitoring"]
    published = service["ports"][0]
    assert monitor["type"] == "http"
    assert monitor["target"] == "http://172.17.0.24:30233/metrics"
    assert monitor["host"] == "172.17.0.24"
    assert monitor["port"] == 30233
    assert monitor["path"] == "/metrics"
    assert int(published["published"]) == monitor["port"]
    assert published["target"] == 30233
