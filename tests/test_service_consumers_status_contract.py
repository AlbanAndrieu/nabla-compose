"""Ensure planned/disabled catalog services are not runtime health expectations."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
HOMARR = ROOT / "apps" / "homarr" / "generated" / "apps.json"
GATUS = ROOT / "apps" / "gatus" / "config" / "config.yml"
AUTOKUMA = ROOT / "apps" / "autokuma" / "static" / "generated-monitors.json"

PLANNED = {
    "akvorado-console": "Akvorado",
    "akvorado-inlet": "Akvorado Inlet",
    "akvorado-orchestrator": "Akvorado Orchestrator",
    "akvorado-outlet": "Akvorado Outlet",
    "crowdsec": "CrowdSec",
    "dsomm": "OWASP DevSecOps Maturity Model",
    "dsomm-baseline": "DSOMM GitHub Baseline",
    "keycloak": "Keycloak",
    "n8n": "n8n",
}


class ServiceConsumerStatusContractTests(unittest.TestCase):
    def test_planned_services_remain_discoverable_but_not_monitored(self) -> None:
        homarr = json.loads(HOMARR.read_text(encoding="utf-8"))
        homarr_ids = {item["id"] for item in homarr["applications"]}
        gatus = yaml.safe_load(GATUS.read_text(encoding="utf-8"))
        gatus_ids = {
            endpoint.get("extra-labels", {}).get("nabla_service_id")
            for endpoint in gatus.get("endpoints", [])
        }
        autokuma = json.loads(AUTOKUMA.read_text(encoding="utf-8"))
        autokuma_names = {item["name"] for item in autokuma}

        for service_id, name in PLANNED.items():
            with self.subTest(service=service_id):
                self.assertIn(service_id, homarr_ids)
                self.assertNotIn(service_id, gatus_ids)
                self.assertNotIn(name, autokuma_names)

    def test_declared_planned_status_matches_compose_sources(self) -> None:
        discovered: set[str] = set()
        for path in sorted((ROOT / "apps").glob("*/compose.yml")):
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for service in (payload.get("services") or {}).values():
                if not isinstance(service, dict):
                    continue
                metadata = service.get("x-nabla")
                if isinstance(metadata, dict) and metadata.get("status") == "planned":
                    discovered.add(metadata["id"])

        self.assertEqual(set(PLANNED), discovered)


if __name__ == "__main__":
    unittest.main()
