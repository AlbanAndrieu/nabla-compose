from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from nabla_ops import InitializationStage, ServiceIntent, declared_apps, normalize_service_intent


def _catalog(status: str | None = None) -> dict:
    service = {
        "id": "example",
        "sourcePath": "apps/example/compose.yml",
        "runtime": {"provider": "truenas-app", "appId": "example"},
    }
    if status is not None:
        service["status"] = status
    return {"services": [service]}


def test_missing_status_falls_back_to_active() -> None:
    assert normalize_service_intent(None) is ServiceIntent.ACTIVE
    assert normalize_service_intent("") is ServiceIntent.ACTIVE


def test_planned_and_disabled_are_not_initialization_eligible() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        compose = root / "apps" / "example" / "compose.yml"
        compose.parent.mkdir(parents=True)
        compose.write_text("services:\n  example:\n    image: example\n", encoding="utf-8")
        for status in ("planned", "disabled"):
            row = declared_apps(_catalog(status), root=root)[0]
            assert row["status"] == status
            assert row["initializationEligible"] is False


def test_active_service_is_initialization_eligible_by_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        compose = root / "apps" / "example" / "compose.yml"
        compose.parent.mkdir(parents=True)
        compose.write_text("services:\n  example:\n    image: example\n", encoding="utf-8")
        row = declared_apps(_catalog(), root=root)[0]
        assert row["status"] == "active"
        assert row["initializationEligible"] is True


def test_manual_profile_is_not_initialization_eligible() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        compose = root / "apps" / "example" / "compose.yml"
        compose.parent.mkdir(parents=True)
        compose.write_text(
            "services:\n  example:\n    image: example\n    profiles:\n      - manual\n",
            encoding="utf-8",
        )
        row = declared_apps(_catalog(), root=root)[0]
        assert row["manual"] is True
        assert row["initializationEligible"] is False


def test_initialization_stage_order_is_stable() -> None:
    assert [stage.value for stage in InitializationStage] == [
        "DECLARED",
        "SECRETS_DECLARED",
        "SECRETS_MATERIALIZED",
        "DEPENDENCIES_READY",
        "DEPLOYED",
        "RUNTIME_ACCEPTED",
        "REBOOT_ACCEPTED",
    ]


def test_cli_is_read_only_and_emits_catalog_json() -> None:
    result = subprocess.run(
        ["python3", str(ROOT / "scripts" / "nabla-service.py"), "catalog", "--json", "--include-non-active"],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    by_app = {row["app"]: row for row in payload}
    assert by_app["opconnect"]["status"] == "disabled"
    assert by_app["opconnect"]["initializationEligible"] is False
    assert by_app["n8n"]["status"] == "planned"
    assert by_app["n8n"]["initializationEligible"] is False
