"""Gatus native monitoring declarations drive both generated consumers."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "config/monitoring/gatus-endpoints.yml"
GATUS = ROOT / "apps/gatus/config/config.yml"
AUTOKUMA = ROOT / "apps/autokuma/static/generated-monitors.json"


def test_native_monitors_are_projected_without_duplication() -> None:
    source = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    gatus = yaml.safe_load(GATUS.read_text(encoding="utf-8"))
    autokuma = json.loads(AUTOKUMA.read_text(encoding="utf-8"))
    native_ids = [ep["extra-labels"]["nabla_monitor_id"]
                  for ep in source["endpoints"]]
    generated_ids = [ep["extra-labels"]["nabla_monitor_id"]
                     for ep in gatus["endpoints"]]
    assert len(native_ids) == len(set(native_ids))
    assert len(generated_ids) == len(set(generated_ids))
    assert set(generated_ids) <= set(native_ids)
    assert len(generated_ids) == len(autokuma)
    assert len({item["name"] for item in autokuma}) == len(autokuma)


def test_http_probe_conditions_survive_projection() -> None:
    native = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))["endpoints"]
    generated = yaml.safe_load(GATUS.read_text(encoding="utf-8"))["endpoints"]
    def by_id(endpoints):
        return {ep["extra-labels"]["nabla_monitor_id"]: ep for ep in endpoints}
    before, after = by_id(native), by_id(generated)
    assert after["autoxpose"]["url"] == before["autoxpose"]["url"]
    assert after["autoxpose"]["conditions"] == before["autoxpose"]["conditions"]
    assert after["autoxpose"]["url"].startswith("http://")
    assert after["pfsense"]["extra-labels"]["nabla_service_id"] == "pfsense"
    assert after["truenas"]["extra-labels"]["nabla_service_id"] == "truenas"
