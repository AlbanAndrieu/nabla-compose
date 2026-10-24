"""Offline safety contracts for Home Assistant/OpenWebUI ID and tunnel cutover."""

from pathlib import Path
import json
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class CanonicalAppMigrationTests(unittest.TestCase):
    def test_compose_identity_without_changing_vendor_image_or_data_mount(self) -> None:
        compose = yaml.safe_load((ROOT / "apps/openwebui/compose.yml").read_text())
        self.assertEqual(list(compose["services"]), ["openwebui"])
        service = compose["services"]["openwebui"]
        self.assertEqual(service["container_name"], "openwebui")
        self.assertEqual(service["x-nabla"]["id"], "openwebui")
        self.assertEqual(service["x-nabla"]["runtime"]["containerService"], "openwebui")
        self.assertEqual(service["x-nabla"]["runtime"]["appId"], "openwebui")
        self.assertEqual(
            service["labels"]["com.albandrieu.nabla.entity-ref"],
            "component:default/openwebui",
        )
        self.assertIn("ghcr.io/open-webui/open-webui:", service["image"])
        self.assertIn("/mnt/cpool/openwebui/data:/app/backend/data", service["volumes"])
        self.assertEqual(service["ports"][0]["published"], "${OPEN_WEBUI_PORT-31028}")
        exposure = service["x-nabla"]["exposure"][0]
        self.assertEqual(exposure["hostnames"], ["openwebui.albandrieu.com"])
        self.assertTrue(exposure["access"]["required"])
        cors = next(item for item in service["environment"] if item.startswith("CORS_ALLOW_ORIGIN="))
        self.assertIn("https://openwebui.albandrieu.com", cors)

    def test_homeassistant_already_uses_canonical_runtime_identity(self) -> None:
        compose = yaml.safe_load((ROOT / "apps/homeassistant/compose.yml").read_text())
        self.assertEqual(list(compose["services"]), ["homeassistant"])
        svc = compose["services"]["homeassistant"]
        self.assertEqual(svc["container_name"], "homeassistant")
        self.assertEqual(svc["x-nabla"]["runtime"]["containerService"], "homeassistant")
        self.assertIn("/mnt/storage0/home-assistant/config:/config", svc["volumes"])

    def test_exposure_catalog_and_private_bichon_policy(self) -> None:
        services = json.loads((ROOT / "catalog/homelab-services.json").read_text())["services"]
        by_id = {item["id"]: item for item in services}
        self.assertNotIn("open-webui", by_id)
        self.assertEqual(by_id["openwebui"]["tunnelUrl"], "https://openwebui.albandrieu.com")
        self.assertEqual(by_id["gatus"]["internalPort"], 8085)
        self.assertEqual(by_id["bichon"]["internalPort"], 15630)
        overrides = json.loads(
            (ROOT / "catalog/homelab-exposure-overrides.json").read_text()
        )["services"]
        bichon = next(item for item in overrides if item["name"] == "Bichon UI")
        self.assertIs(bichon["external"], False)

    def test_rename_script_is_fail_closed_and_does_not_mutate_cloudflare(self) -> None:
        script = (ROOT / "scripts/truenas/migrate-homeassistant-openwebui-names.sh").read_text()
        self.assertIn('mode="--check"', script)
        self.assertIn('"--apply"', script)
        self.assertIn('NABLA_RUNTIME_CHANGE_APPROVED', script)
        self.assertIn('"$old_project" == "openwebui"', script)
        self.assertIn('docker rename open-webui "$backup"', script)
        self.assertIn('docker rename "$backup" open-webui', script)
        self.assertIn('TrueNAS', script)
        self.assertNotIn("docker compose down", script)
        self.assertNotIn("docker volume rm", script)
        self.assertNotIn("cloudflared tunnel route dns", script)


if __name__ == "__main__":
    unittest.main()
