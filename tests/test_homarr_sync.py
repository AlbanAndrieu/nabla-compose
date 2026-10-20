"""Unit tests for the non-destructive Homarr v2 reconciler."""

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

GRAFANA = {"id": "grafana", "name": "Grafana", "href": "https://grafana.example.test", "syncEligible": True}
PFSENSE = {"id": "pfsense", "name": "pfSense", "href": "https://pfsense.example.test", "syncEligible": True}


def _boards(*boards: dict) -> dict:
    return {"version": 1, "boards": list(boards)}


def _reconcile(definitions: object, request_json: Mock, state: dict[str, str], *, dry_run: bool = False):
    with (
        patch.object(homarr_sync, "BOARD_SYNC_ENABLED", True),
        patch.object(homarr_sync, "DRY_RUN", dry_run),
        patch.object(homarr_sync, "load_json", return_value=definitions),
        patch.object(homarr_sync, "request_json", request_json),
    ):
        return homarr_sync.reconcile_board(state, [GRAFANA, PFSENSE])


class HomarrSyncTests(unittest.TestCase):
    def test_find_existing_prefers_persisted_mapping(self) -> None:
        desired = {
            "name": "Grafana",
            "description": None,
            "iconUrl": "https://example.test/grafana.svg",
            "href": "https://grafana.example.test",
        }
        apps = [
            {"id": "mapped", "name": "Old Grafana", "href": "https://old.example.test"},
            {"id": "other", "name": "Grafana", "href": "https://grafana.example.test"},
        ]

        existing = homarr_sync.find_existing(desired, apps, "mapped")

        self.assertIsNotNone(existing)
        self.assertEqual(existing["id"], "mapped")

    def test_desired_payload_uses_safe_default_icon_without_ping_url(self) -> None:
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
        # Homarr v2 dropped pingUrl from the app payload.
        self.assertNotIn("pingUrl", payload)

    def test_main_creates_and_updates_without_deleting(self) -> None:
        manifest = {
            "applications": [
                GRAFANA,
                PFSENSE,
                {"id": "worker", "name": "Worker", "href": None, "syncEligible": False},
            ]
        }
        existing_apps = [
            {
                "id": "homarr-grafana",
                "name": "Grafana old",
                "description": None,
                "iconUrl": homarr_sync.DEFAULT_ICON,
                "href": "https://grafana.example.test",
            }
        ]
        request_json = Mock(side_effect=[None, {"id": "homarr-pfsense", "name": "pfSense"}])

        def fake_load_json(path: Path, fallback: object) -> object:
            return manifest if path == homarr_sync.MANIFEST_PATH else fallback

        with (
            patch.object(homarr_sync, "API_KEY", "test-api-key"),
            patch.object(homarr_sync, "BOARD_SYNC_ENABLED", False),
            patch.object(homarr_sync, "DRY_RUN", False),
            patch.object(homarr_sync, "load_json", side_effect=fake_load_json),
            patch.object(homarr_sync, "wait_for_homarr", return_value=existing_apps.copy()),
            patch.object(homarr_sync, "request_json", request_json),
        ):
            result = homarr_sync.main()

        self.assertEqual(result, 0)
        payload = {"description": None, "iconUrl": homarr_sync.DEFAULT_ICON}
        self.assertEqual(
            request_json.call_args_list,
            [
                call("PATCH", "/api/apps/homarr-grafana",
                     {"name": "Grafana", **payload, "href": "https://grafana.example.test"}),
                call("POST", "/api/apps",
                     {"name": "pfSense", **payload, "href": "https://pfsense.example.test"}),
            ],
        )
        self.assertFalse(any(args[0] == "DELETE" for args, _ in request_json.call_args_list))

    def test_reconcile_board_creates_and_populates_from_remote_membership(self) -> None:
        state = {"grafana": "homarr-grafana", "pfsense": "homarr-pfsense"}
        request_json = Mock(side_effect=[
            [],
            {"boardId": "board-nabla"},
            [],
            {"itemId": "item-grafana"},
            {"itemId": "item-pfsense"},
        ])

        created, added = _reconcile(
            _boards({"name": "Nabla", "columns": 12, "public": False, "applications": "*"}),
            request_json, state,
        )

        self.assertTrue(created)
        self.assertEqual(added, 2)
        item = {"boardId": "board-nabla", "kind": "app", "integrationIds": []}
        self.assertEqual(
            request_json.call_args_list,
            [
                call("GET", "/api/boards"),
                call("POST", "/api/boards", {"name": "Nabla", "columnCount": 12, "isPublic": False}),
                call("GET", "/api/boards/board-nabla/items"),
                call("POST", "/api/boards/items", {**item, "options": {"appId": "homarr-grafana"}}),
                call("POST", "/api/boards/items", {**item, "options": {"appId": "homarr-pfsense"}}),
            ],
        )

    def test_reconcile_board_is_idempotent_against_existing_items(self) -> None:
        state = {"grafana": "homarr-grafana", "pfsense": "homarr-pfsense"}
        request_json = Mock(side_effect=[
            [{"id": "board-nabla", "name": "Nabla"}],
            [{"options": {"appId": "homarr-grafana"}}, {"options": {"appId": "homarr-pfsense"}}],
        ])

        created, added = _reconcile(_boards({"name": "Nabla", "applications": "*"}), request_json, state)

        self.assertEqual((created, added), (False, 0))
        self.assertFalse(any(args[0] in {"POST", "DELETE"} for args, _ in request_json.call_args_list))

    def test_reconcile_board_refuses_ambiguous_board_names(self) -> None:
        request_json = Mock(return_value=[{"id": "a", "name": "Nabla"}, {"id": "b", "name": "Nabla"}])

        with self.assertRaisesRegex(RuntimeError, "ambiguous board name: Nabla"):
            _reconcile(_boards({"name": "Nabla", "applications": "*"}), request_json, {})

    def test_reconcile_board_rejects_unknown_applications(self) -> None:
        request_json = Mock(side_effect=[[{"id": "board-sec", "name": "Security"}], []])

        with self.assertRaisesRegex(ValueError, "unknown or ineligible application crowdsec"):
            _reconcile(_boards({"name": "Security", "applications": ["crowdsec"]}), request_json, {})

    def test_reconcile_board_requires_versioned_configuration(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires version: 1"):
            _reconcile({"boards": []}, Mock(), {})

    def test_dry_run_never_creates_boards(self) -> None:
        request_json = Mock(return_value=[])

        created, added = _reconcile(_boards({"name": "Nabla", "applications": "*"}), request_json, {}, dry_run=True)

        self.assertEqual((created, added), (False, 0))
        request_json.assert_called_once_with("GET", "/api/boards")

    def test_committed_boards_configuration_is_versioned(self) -> None:
        definitions = homarr_sync.load_json(MODULE_PATH.parent / "config" / "boards.json", {})
        self.assertEqual(definitions["version"], 1)
        self.assertTrue(all(board["name"] for board in definitions["boards"]))


if __name__ == "__main__":
    unittest.main()
