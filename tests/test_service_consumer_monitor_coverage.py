"""Cross-check active monitoring declarations against generated Gatus endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog" / "services.json"
GATUS = ROOT / "apps" / "gatus" / "config" / "config.yml"


def test_every_active_monitored_service_has_gatus_service_identity() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    gatus = yaml.safe_load(GATUS.read_text(encoding="utf-8"))

    active_monitored = {
        service["id"]
        for service in catalog["services"]
        if service.get("status", "active") == "active"
        and isinstance(service.get("monitoring"), dict)
        and service["monitoring"].get("enabled") is not False
    }
    generated = {
        labels["nabla_service_id"]
        for endpoint in gatus["endpoints"]
        if isinstance((labels := endpoint.get("extra-labels")), dict)
        and isinstance(labels.get("nabla_service_id"), str)
    }

    assert active_monitored <= generated
    assert "doco-cd" in generated


def test_planned_and_disabled_monitors_are_not_required_in_gatus() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    gatus = yaml.safe_load(GATUS.read_text(encoding="utf-8"))
    generated = {
        labels["nabla_service_id"]
        for endpoint in gatus["endpoints"]
        if isinstance((labels := endpoint.get("extra-labels")), dict)
        and isinstance(labels.get("nabla_service_id"), str)
    }

    inactive_monitored = {
        service["id"]
        for service in catalog["services"]
        if service.get("status", "active") in {"planned", "disabled"}
        and isinstance(service.get("monitoring"), dict)
    }
    assert inactive_monitored.isdisjoint(generated)
