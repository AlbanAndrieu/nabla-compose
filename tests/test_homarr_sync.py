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
            patch.object(homarr_sync, "BOARD_SYNC_ENABLED", False),
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
        self.assertFalse(
            any(args[0] == "DELETE" for args, _ in request_json.call_args_list)
        )

    def test_reconcile_board_creates_and_populates_once(self) -> None:
        state = {
            "grafana": "homarr-grafana",
            "pfsense": "homarr-pfsense",
        }
        desired_items = [
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
        ]
        request_json = Mock()
        request_json.side_effect = [
            [],
            {"boardId": "board-nabla"},
            {"itemId": "item-grafana"},
            {"itemId": "item-pfsense"},
        ]

        with (
            patch.object(homarr_sync, "BOARD_SYNC_ENABLED", True),
            patch.object(homarr_sync, "BOARD_NAME", "Nabla"),
            patch.object(homarr_sync, "BOARD_COLUMN_COUNT", 12),
            patch.object(homarr_sync, "BOARD_PUBLIC", False),
            patch.object(homarr_sync, "DRY_RUN", False),
            patch.object(homarr_sync, "request_json", request_json),
        ):
            created, added = homarr_sync.reconcile_board(state, desired_items)

        self.assertTrue(created)
        self.assertEqual(added, 2)
        self.assertEqual(state["__board__:nabla"], "board-nabla")
        self.assertEqual(
            state["__board_item__:nabla:grafana"],
            "item-grafana",
        )
        self.assertEqual(
            state["__board_item__:nabla:pfsense"],
            "item-pfsense",
        )
        self.assertEqual(
            request_json.call_args_list,
            [
                call("GET", "/api/boards"),
                call(
                    "POST",
                    "/api/boards",
                    {"name": "Nabla", "columnCount": 12, "isPublic": False},
                ),
                call(
                    "POST",
                    "/api/boards/items",
                    {
                        "boardId": "board-nabla",
                        "kind": "app",
                        "options": {"appId": "homarr-grafana"},
                        "integrationIds": [],
                    },
                ),
                call(
                    "POST",
                    "/api/boards/items",
                    {
                        "boardId": "board-nabla",
                        "kind": "app",
                        "options": {"appId": "homarr-pfsense"},
                        "integrationIds": [],
                    },
                ),
            ],
        )

        second_request = Mock(return_value=[{"id": "board-nabla", "name": "Nabla"}])
        with (
            patch.object(homarr_sync, "BOARD_SYNC_ENABLED", True),
            patch.object(homarr_sync, "BOARD_NAME", "Nabla"),
            patch.object(homarr_sync, "DRY_RUN", False),
            patch.object(homarr_sync, "request_json", second_request),
        ):
            created_again, added_again = homarr_sync.reconcile_board(
                state,
                desired_items,
            )

        self.assertFalse(created_again)
        self.assertEqual(added_again, 0)
        second_request.assert_called_once_with("GET", "/api/boards")

    def test_reconcile_board_leaves_unmanaged_existing_board_untouched(self) -> None:
        state = {"grafana": "homarr-grafana"}
        desired_items = [
            {
                "id": "grafana",
                "name": "Grafana",
                "href": "https://grafana.example.test",
                "syncEligible": True,
            }
        ]
        request_json = Mock(return_value=[{"id": "user-board", "name": "Nabla"}])

        with (
            patch.object(homarr_sync, "BOARD_SYNC_ENABLED", True),
            patch.object(homarr_sync, "BOARD_NAME", "Nabla"),
            patch.object(homarr_sync, "DRY_RUN", False),
            patch.object(homarr_sync, "request_json", request_json),
        ):
            created, added = homarr_sync.reconcile_board(state, desired_items)

        self.assertFalse(created)
        self.assertEqual(added, 0)
        self.assertNotIn("__board__:nabla", state)
        request_json.assert_called_once_with("GET", "/api/boards")

    def test_reconcile_board_refuses_to_recreate_deleted_managed_board(self) -> None:
        state = {
            "grafana": "homarr-grafana",
            "__board__:nabla": "deleted-board",
        }
        desired_items = [
            {
                "id": "grafana",
                "name": "Grafana",
                "href": "https://grafana.example.test",
                "syncEligible": True,
            }
        ]
        request_json = Mock(return_value=[])

        with (
            patch.object(homarr_sync, "BOARD_SYNC_ENABLED", True),
            patch.object(homarr_sync, "BOARD_NAME", "Nabla"),
            patch.object(homarr_sync, "DRY_RUN", False),
            patch.object(homarr_sync, "request_json", request_json),
        ):
            created, added = homarr_sync.reconcile_board(state, desired_items)

        self.assertFalse(created)
        self.assertEqual(added, 0)
        request_json.assert_called_once_with("GET", "/api/boards")


if __name__ == "__main__":
    unittest.main()
