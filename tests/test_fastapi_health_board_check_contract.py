"""Contracts for the HTTP-only FastAPI health-board checker."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "truenas" / "check-fastapi-health-board.sh"


def test_health_board_checker_is_http_only_and_waits_for_homelab() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "/api/health-board?refresh=true" not in source
    assert '"${endpoint}?refresh=true"' in source
    assert ".homelab != null" in source
    assert ".refreshing == false" in source
    assert '.state == "fresh" or .state == "stale"' in source
    assert "Health-board pending" in source
    assert "Health-board converged" in source
    assert "DIAGNOSTICS_ACCESS_KEY are not used" in source
    assert "ssh " not in source
    assert "docker exec" not in source


def test_health_board_checker_exposes_truenas_and_pfsense_evidence() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    for token in (
        "appliance_state",
        "public_ingress_state",
        "path_mode",
        "connect_target",
        "api_authenticated",
        "api_evidence_state",
        "endpoint_status",
        "security_filters",
        "ingress_block",
    ):
        assert token in source


def test_health_board_checker_shell_syntax() -> None:
    syntax = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr
