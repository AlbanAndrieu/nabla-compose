"""Native Gatus monitors must respect Backstage operational state."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
HOMARR = ROOT / "apps/homarr/generated/apps.json"
GATUS = ROOT / "apps/gatus/config/config.yml"
AUTOKUMA = ROOT / "apps/autokuma/static/generated-monitors.json"
NATIVE = ROOT / "config/monitoring/gatus-endpoints.yml"


def backstage_states() -> dict[str, str]:
    paths = [ROOT / "catalog/catalog-info.yaml"]
    paths.extend(sorted((ROOT / "apps").glob("*/catalog-info.yaml")))
    return {
        entity["metadata"]["name"]: (entity["metadata"].get("labels") or {}).get(
            "albandrieu.com/operational-state", "active"
        )
        for path in paths
        for entity in yaml.safe_load_all(path.read_text(encoding="utf-8"))
        if isinstance(entity, dict) and entity.get("kind") in {"Component", "Resource", "API"}
    }


class ServiceConsumerStatusContractTests(unittest.TestCase):
    def test_inactive_backstage_entities_are_not_probed(self) -> None:
        inactive = {id for id, state in backstage_states().items()
                    if state in {"planned", "disabled"}}
        gatus = yaml.safe_load(GATUS.read_text(encoding="utf-8"))
        monitored = {ep.get("extra-labels", {}).get("nabla_service_id")
                     for ep in gatus["endpoints"]}
        self.assertTrue(inactive.isdisjoint(monitored))
        # Homarr can still display planned apps; discovery != runtime health.
        homarr = json.loads(HOMARR.read_text(encoding="utf-8"))
        self.assertEqual(len({app["id"] for app in homarr["applications"]}),
                         len(homarr["applications"]))

    def test_native_doco_cd_probe_is_projected_unchanged(self) -> None:
        source = yaml.safe_load(NATIVE.read_text(encoding="utf-8"))
        gatus = yaml.safe_load(GATUS.read_text(encoding="utf-8"))
        declared = next(ep for ep in source["endpoints"]
                        if ep.get("extra-labels", {}).get("nabla_monitor_id") == "doco-cd")
        generated = next(ep for ep in gatus["endpoints"]
                         if ep.get("extra-labels", {}).get("nabla_monitor_id") == "doco-cd")
        self.assertEqual(generated["url"], declared["url"])
        self.assertEqual(generated["conditions"], declared["conditions"])
        self.assertEqual(generated["extra-labels"]["nabla_service_id"], "doco-cd")
        kuma = json.loads(AUTOKUMA.read_text(encoding="utf-8"))
        candidate = next(item for item in kuma if item["name"] == generated["name"])
        self.assertEqual(candidate["type"], "port")
        self.assertEqual(candidate["port"], int(declared["url"].rsplit(":", 1)[-1]))


if __name__ == "__main__":
    unittest.main()
