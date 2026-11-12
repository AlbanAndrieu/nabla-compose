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


def _board_items(*items: dict) -> dict:
    """tRPC board.getBoardByName response, reduced to its items."""
    return {"result": {"data": {"json": {"items": list(items)}}}}


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

    def test_desired_payload_uses_safe_default_icon_and_null_ping_url(self) -> None:
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
        # Homarr v2.6 rejects a create or edit without the pingUrl key.
        self.assertIsNone(payload["pingUrl"])

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
                "pingUrl": "https://grafana.example.test/api/health",
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
                     {"name": "Grafana", **payload, "href": "https://grafana.example.test",
                      "pingUrl": "https://grafana.example.test/api/health"}),
                call("POST", "/api/apps",
                     {"name": "pfSense", **payload, "href": "https://pfsense.example.test", "pingUrl": None}),
            ],
        )
        self.assertFalse(any(args[0] == "DELETE" for args, _ in request_json.call_args_list))

    def test_reconcile_board_creates_and_populates_from_remote_membership(self) -> None:
        state = {"grafana": "homarr-grafana", "pfsense": "homarr-pfsense"}
        request_json = Mock(side_effect=[
            [],
            {"boardId": "board-nabla"},
            _board_items(),
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
                call("GET", "/api/trpc/board.getBoardByName?input=%7B%22json%22%3A%20%7B%22name%22%3A%20%22Nabla%22%7D%7D"),
                call("POST", "/api/boards/items", {**item, "options": {"appId": "homarr-grafana"}}),
                call("POST", "/api/boards/items", {**item, "options": {"appId": "homarr-pfsense"}}),
            ],
        )

    def test_code_managed_board_is_recreated_after_manual_deletion(self) -> None:
        # boards.json is the source of truth: a deleted declared board comes back.
        state = {"grafana": "homarr-grafana", "pfsense": "homarr-pfsense"}
        request_json = Mock(side_effect=[
            [{"id": "user-board", "name": "Personal"}],
            {"boardId": "board-infra"},
            _board_items(),
            {"itemId": "item-pfsense"},
        ])

        created, added = _reconcile(
            _boards({"name": "Infrastructure", "applications": ["pfsense"]}), request_json, state,
        )

        self.assertEqual((created, added), (True, 1))
        self.assertIn(
            call("POST", "/api/boards", {"name": "Infrastructure", "columnCount": 12, "isPublic": False}),
            request_json.call_args_list,
        )
        # Unrelated user boards are never touched or deleted.
        self.assertFalse(any("user-board" in str(args) for args, _ in request_json.call_args_list[1:]))
        self.assertFalse(any(args[0] == "DELETE" for args, _ in request_json.call_args_list))

    def test_reconcile_board_is_idempotent_against_existing_items(self) -> None:
        state = {"grafana": "homarr-grafana", "pfsense": "homarr-pfsense"}
        request_json = Mock(side_effect=[
            [{"id": "board-nabla", "name": "Nabla"}],
            _board_items({"options": {"appId": "homarr-grafana"}}, {"options": {"appId": "homarr-pfsense"}}),
        ])

        created, added = _reconcile(_boards({"name": "Nabla", "applications": "*"}), request_json, state)

        self.assertEqual((created, added), (False, 0))
        self.assertFalse(any(args[0] in {"POST", "DELETE"} for args, _ in request_json.call_args_list))

    def test_reconcile_board_refuses_ambiguous_board_names(self) -> None:
        request_json = Mock(return_value=[{"id": "a", "name": "Nabla"}, {"id": "b", "name": "Nabla"}])

        with self.assertRaisesRegex(RuntimeError, "ambiguous board name: Nabla"):
            _reconcile(_boards({"name": "Nabla", "applications": "*"}), request_json, {})

    def test_reconcile_board_rejects_unknown_applications(self) -> None:
        request_json = Mock(side_effect=[[{"id": "board-sec", "name": "Security"}], _board_items()])

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


def test_missing_key_skips_without_crashing_the_truenas_app(capsys) -> None:
    with patch.object(homarr_sync, "API_KEY", ""):
        assert homarr_sync.main() == 0
    assert "RECONCILE_SKIPPED" in capsys.readouterr().out + capsys.readouterr().err


def test_legacy_token_name_is_accepted_but_flagged() -> None:
    source = (Path(__file__).resolve().parents[1] / "apps/homarr/sync.py").read_text(encoding="utf-8")
    assert 'os.getenv("HOMARR_API_KEY") or os.getenv("HOMARR_API_TOKEN")' in source
    assert "rematerialise HOMARR_API_KEY" in source


def test_rejected_key_skips_at_once_without_crashing_the_truenas_app(capsys) -> None:
    request_json = Mock(side_effect=homarr_sync.AuthRejected("Homarr API GET /api/apps returned 401"))
    with (
        patch.object(homarr_sync, "API_KEY", "revoked"),
        patch.object(homarr_sync, "load_json", return_value={"applications": [GRAFANA]}),
        patch.object(homarr_sync, "request_json", request_json),
        patch.object(homarr_sync.time, "sleep") as sleep,
    ):
        assert homarr_sync.main() == 0
    assert request_json.call_count == 1
    sleep.assert_not_called()
    assert "RECONCILE_SKIPPED" in capsys.readouterr().out


def test_read_timeout_keeps_waiting_for_the_api() -> None:
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = b"[]"
    with (
        patch.object(homarr_sync, "urlopen", side_effect=[TimeoutError("timed out"), response]) as urlopen,
        patch.object(homarr_sync.time, "sleep"),
    ):
        assert homarr_sync.wait_for_homarr() == []
    assert urlopen.call_count == 2


def test_assistant_points_homarr_at_litellm_through_trpc() -> None:
    request_json = Mock(return_value=None)
    with (
        patch.object(homarr_sync, "ASSISTANT_API_KEY", "virtual-key"),
        patch.object(homarr_sync, "DRY_RUN", False),
        patch.object(homarr_sync, "request_json", request_json),
    ):
        assert homarr_sync.reconcile_assistant() == "connected"
    connection, configuration = request_json.call_args_list
    assert connection == call("POST", "/api/trpc/assistant.updateConnection", {"json": {
        "provider": "custom", "baseUrl": "http://172.17.0.24:4000/v1",
        "modelDiscoveryPath": "/models", "apiKey": "virtual-key"}})
    assert configuration == call("POST", "/api/trpc/assistant.updateConfiguration", {"json": {
        "enabled": True, "modelId": "qwen", "webSearchEnabled": False}})


def test_assistant_without_key_sends_nothing() -> None:
    request_json = Mock()
    with (
        patch.object(homarr_sync, "ASSISTANT_API_KEY", ""),
        patch.object(homarr_sync, "request_json", request_json),
    ):
        assert homarr_sync.reconcile_assistant() == "skipped_no_key"
    request_json.assert_not_called()


def test_assistant_failure_neither_crashes_nor_logs_the_error_body(capsys) -> None:
    failure = RuntimeError("Homarr API POST /api/trpc/assistant.updateConnection returned 400: echoed-body")
    with (
        patch.object(homarr_sync, "API_KEY", "test-api-key"),
        patch.object(homarr_sync, "ASSISTANT_API_KEY", "virtual-key"),
        patch.object(homarr_sync, "BOARD_SYNC_ENABLED", False),
        patch.object(homarr_sync, "DRY_RUN", False),
        patch.object(homarr_sync, "load_json", return_value={"applications": []}),
        patch.object(homarr_sync, "wait_for_homarr", return_value=[]),
        patch.object(homarr_sync, "request_json", Mock(side_effect=failure)),
    ):
        assert homarr_sync.main() == 0
    out = capsys.readouterr().out
    assert "ASSISTANT_RECONCILE_FAILED" in out
    assert "assistant=failed" in out
    assert "echoed-body" not in out
