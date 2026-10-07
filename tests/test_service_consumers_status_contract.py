"""Ensure inactive catalog services are not runtime health expectations."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
HOMARR = ROOT / "apps" / "homarr" / "generated" / "apps.json"
GATUS = ROOT / "apps" / "gatus" / "config" / "config.yml"
AUTOKUMA = ROOT / "apps" / "autokuma" / "static" / "generated-monitors.json"


def inactive_services() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted((ROOT / "apps").glob("*/compose*.yml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for service in (payload.get("services") or {}).values():
            if not isinstance(service, dict):
                continue
            metadata = service.get("x-nabla")
            if not isinstance(metadata, dict):
                continue
            if metadata.get("status") not in {"planned", "disabled"}:
                continue
            result[metadata["id"]] = metadata["name"]
    return result


class ServiceConsumerStatusContractTests(unittest.TestCase):
    def test_inactive_services_remain_discoverable_but_not_monitored(self) -> None:
        inactive = inactive_services()
        self.assertTrue(inactive, "expected at least one planned/disabled service fixture")

        homarr = json.loads(HOMARR.read_text(encoding="utf-8"))
        homarr_ids = {item["id"] for item in homarr["applications"]}

        gatus = yaml.safe_load(GATUS.read_text(encoding="utf-8"))
        gatus_ids = {
            endpoint.get("extra-labels", {}).get("nabla_service_id")
            for endpoint in gatus.get("endpoints", [])
        }

        autokuma = json.loads(AUTOKUMA.read_text(encoding="utf-8"))
        autokuma_names = {item["name"] for item in autokuma}

        for service_id, name in inactive.items():
            with self.subTest(service=service_id):
                self.assertIn(service_id, homarr_ids)
                self.assertNotIn(service_id, gatus_ids)
                self.assertNotIn(name, autokuma_names)


    def test_active_root_monitoring_is_exported_to_consumers(self) -> None:
        catalog = json.loads(
            (ROOT / "catalog" / "services.json").read_text(encoding="utf-8")
        )
        doco = next(item for item in catalog["services"] if item["id"] == "doco-cd")
        self.assertEqual(doco.get("status", "active"), "active")
        self.assertEqual(
            doco["monitoring"],
            {"type": "port", "host": "172.17.0.24", "port": 9120},
        )

        gatus = yaml.safe_load(GATUS.read_text(encoding="utf-8"))
        endpoints = {
            endpoint.get("extra-labels", {}).get("nabla_service_id"): endpoint
            for endpoint in gatus.get("endpoints", [])
        }
        self.assertEqual(
            endpoints["doco-cd"]["url"],
            "tcp://172.17.0.24:9120",
        )

        autokuma = json.loads(AUTOKUMA.read_text(encoding="utf-8"))
        generated = next(item for item in autokuma if item["name"] == "Doco-CD")
        self.assertEqual(
            (generated["type"], generated["hostname"], generated["port"]),
            ("port", "172.17.0.24", 9120),
        )


if __name__ == "__main__":
    unittest.main()
