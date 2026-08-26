"""Unit tests for the non-destructive Homarr reconciler."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "apps" / "homarr" / "sync.py"
SPEC = importlib.util.spec_from_file_location("homarr_sync", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
homarr_sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(homarr_sync)


class HomarrSyncTests(unittest.TestCase):
    def test_find_existing_prefers_persisted_mapping(self) -> None:
        desired = {
            "name": "Grafana",
            "description": None,
            "iconUrl": "https://example.test/grafana.svg",
            "href": "https://grafana.example.test",
            "pingUrl": "",
        }
        apps = [
            {"id": "mapped", "name": "Old Grafana", "href": "https://old.example.test"},
            {"id": "other", "name": "Grafana", "href": "https://grafana.example.test"},
        ]

        existing = homarr_sync.find_existing(desired, apps, "mapped")

        self.assertIsNotNone(existing)
        self.assertEqual(existing["id"], "mapped")

    def test_desired_payload_uses_safe_default_icon(self) -> None:
        item = {
            "name": "pfSense",
            "href": "https://pfsense.example.test",
            "description": "Firewall",
            "icon": "🔥",
        }

        payload = homarr_sync.desired_payload(item)

        self.assertEqual(payload["name"], "pfSense")
        self.assertEqual(payload["href"], "https://pfsense.example.test")
        self.assertEqual(payload["description"], "Firewall")
        self.assertEqual(payload["iconUrl"], homarr_sync.DEFAULT_ICON)
        self.assertEqual(payload["pingUrl"], "")

    def test_main_creates_and_updates_without_deleting(self) -> None:
        manifest = {
            "applications": [
                {
                    "id": "grafana",
                    "name": "Grafana",
                    "href": "https://grafana.example.test",
                    "syncEligible": True,
                },
                {
                    "id": "pfsense",
                    "name": "pfSense",
                    "href": "https://pfsense.example.test",
                    "syncEligible": True,
                },
                {
                    "id": "worker",
                    "name": "Worker",
                    "href": None,
                    "syncEligible": False,
                },
            ]
        }
        state = {"grafana": "homarr-grafana"}
        existing_apps = [
            {
                "id": "homarr-grafana",
                "name": "Grafana old",
                "description": None,
                "iconUrl": homarr_sync.DEFAULT_ICON,
                "href": "https://grafana.example.test",
                "pingUrl": None,
            }
        ]
        request_json = Mock()
        request_json.side_effect = [
            None,
            {
                "id": "homarr-pfsense",
                "name": "pfSense",
                "description": None,
                "iconUrl": homarr_sync.DEFAULT_ICON,
                "href": "https://pfsense.example.test",
                "pingUrl": None,
            },
        ]
        saved_state: dict[str, str] = {}

        def fake_load_json(path: Path, fallback: object) -> object:
            if path == homarr_sync.MANIFEST_PATH:
                return manifest
            if path == homarr_sync.STATE_PATH:
                return state
            return fallback

        def fake_save_state(value: dict[str, str]) -> None:
            saved_state.update(value)

        with (
            patch.object(homarr_sync, "API_KEY", "test-api-key"),
            patch.object(homarr_sync, "load_json", side_effect=fake_load_json),
            patch.object(homarr_sync, "wait_for_homarr", return_value=existing_apps.copy()),
            patch.object(homarr_sync, "request_json", request_json),
            patch.object(homarr_sync, "save_state", side_effect=fake_save_state),
        ):
            result = homarr_sync.main()

        self.assertEqual(result, 0)
        self.assertEqual(
            request_json.call_args_list,
            [
                call(
                    "PATCH",
                    "/api/apps/homarr-grafana",
                    {
                        "name": "Grafana",
                        "description": None,
                        "iconUrl": homarr_sync.DEFAULT_ICON,
                        "href": "https://grafana.example.test",
                        "pingUrl": "",
                    },
                ),
                call(
                    "POST",
                    "/api/apps",
                    {
                        "name": "pfSense",
                        "description": None,
                        "iconUrl": homarr_sync.DEFAULT_ICON,
                        "href": "https://pfsense.example.test",
                        "pingUrl": "",
                    },
                ),
            ],
        )
        self.assertEqual(
            saved_state,
            {"grafana": "homarr-grafana", "pfsense": "homarr-pfsense"},
        )
        self.assertFalse(any(args[0] == "DELETE" for args, _ in request_json.call_args_list))


if __name__ == "__main__":
    unittest.main()
