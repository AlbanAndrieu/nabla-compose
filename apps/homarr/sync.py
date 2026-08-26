#!/usr/bin/env python3
"""Reconcile generated Nabla applications and dashboard into Homarr."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = os.getenv("HOMARR_BASE_URL", "http://homarr:7575").rstrip("/")
API_KEY = os.getenv("HOMARR_API_KEY", "").strip()
MANIFEST_PATH = Path(os.getenv("HOMARR_MANIFEST", "/config/nabla/apps.json"))
STATE_PATH = Path(os.getenv("HOMARR_SYNC_STATE", "/state/homarr-map.json"))
DRY_RUN = os.getenv("HOMARR_SYNC_DRY_RUN", "false").lower() in {"1", "true", "yes", "on"}
MAX_ATTEMPTS = int(os.getenv("HOMARR_SYNC_ATTEMPTS", "20"))
RETRY_SECONDS = float(os.getenv("HOMARR_SYNC_RETRY_SECONDS", "3"))
DEFAULT_ICON = os.getenv(
    "HOMARR_DEFAULT_ICON_URL",
    "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons@master/svg/homarr.svg",
)
BOARD_SYNC_ENABLED = os.getenv("HOMARR_BOARD_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
BOARD_NAME = os.getenv("HOMARR_BOARD_NAME", "Nabla").strip() or "Nabla"
BOARD_COLUMN_COUNT = int(os.getenv("HOMARR_BOARD_COLUMNS", "12"))
BOARD_PUBLIC = os.getenv("HOMARR_BOARD_PUBLIC", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def log(message: str) -> None:
    print(f"[homarr-sync] {message}", flush=True)


def request_json(method: str, path: str, payload: object | None = None) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "ApiKey": API_KEY,
        },
    )
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - configured private Homarr endpoint
            body = response.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Homarr API {method} {path} returned {exc.code}: {body[:400]}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            f"Homarr API {method} {path} unavailable: {exc.reason}"
        ) from exc
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def load_json(path: Path, fallback: object) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict[str, str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(STATE_PATH)


def wait_for_homarr() -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            apps = request_json("GET", "/api/apps")
            if isinstance(apps, list):
                return [app for app in apps if isinstance(app, dict)]
            raise RuntimeError("Homarr /api/apps did not return an array")
        except (RuntimeError, json.JSONDecodeError) as exc:
            last_error = exc
            log(f"API not ready ({attempt}/{MAX_ATTEMPTS}): {exc}")
            time.sleep(RETRY_SECONDS)
    raise RuntimeError(f"Homarr did not become ready: {last_error}")


def desired_payload(item: dict[str, Any]) -> dict[str, Any]:
    icon = item.get("iconUrl")
    if not isinstance(icon, str) or not icon.startswith(("http://", "https://")):
        icon = DEFAULT_ICON
    description = item.get("description")
    return {
        "name": str(item["name"])[:64],
        "description": str(description)[:512] if description else None,
        "iconUrl": icon,
        "href": str(item["href"]),
        "pingUrl": "",
    }


def find_existing(
    desired: dict[str, Any],
    apps: list[dict[str, Any]],
    mapped_id: str | None,
) -> dict[str, Any] | None:
    if mapped_id:
        mapped = [app for app in apps if app.get("id") == mapped_id]
        if len(mapped) == 1:
            return mapped[0]

    exact = [
        app
        for app in apps
        if app.get("name") == desired.get("name")
        and app.get("href") == desired.get("href")
    ]
    if len(exact) == 1:
        return exact[0]

    same_href = [app for app in apps if app.get("href") == desired.get("href")]
    if len(same_href) == 1:
        return same_href[0]
    return None


def differs(existing: dict[str, Any], desired: dict[str, Any]) -> bool:
    for key in ("name", "description", "iconUrl", "href"):
        if existing.get(key) != desired.get(key):
            return True
    existing_ping = existing.get("pingUrl") or ""
    return existing_ping != desired.get("pingUrl", "")


def board_state_key() -> str:
    return f"__board__:{BOARD_NAME.casefold()}"


def board_item_state_key(nabla_id: str) -> str:
    return f"__board_item__:{BOARD_NAME.casefold()}:{nabla_id}"


def find_board(boards: list[dict[str, Any]]) -> dict[str, Any] | None:
    matches = [
        board
        for board in boards
        if str(board.get("name", "")).casefold() == BOARD_NAME.casefold()
    ]
    if len(matches) > 1:
        raise RuntimeError(f"multiple Homarr boards are named {BOARD_NAME!r}")
    return matches[0] if matches else None


def reconcile_board(
    state: dict[str, str],
    desired_items: list[dict[str, Any]],
) -> tuple[bool, int]:
    """Create/populate the managed Nabla board without deleting user content."""
    if not BOARD_SYNC_ENABLED:
        log("Homarr board reconciliation is disabled")
        return False, 0
    if not 1 <= BOARD_COLUMN_COUNT <= 24:
        raise ValueError("HOMARR_BOARD_COLUMNS must be between 1 and 24")

    raw_boards = request_json("GET", "/api/boards")
    if not isinstance(raw_boards, list):
        raise RuntimeError("Homarr /api/boards did not return an array")
    boards = [board for board in raw_boards if isinstance(board, dict)]
    existing = find_board(boards)
    state_key = board_state_key()
    mapped_board_id = state.get(state_key)
    created_board = False

    if existing is None:
        if mapped_board_id:
            log(
                f"managed board {BOARD_NAME!r} is missing; refusing to recreate it "
                "automatically after an external deletion"
            )
            return False, 0
        if DRY_RUN:
            log(
                f"would create Homarr board {BOARD_NAME!r} "
                f"with {BOARD_COLUMN_COUNT} columns"
            )
            return False, 0
        result = request_json(
            "POST",
            "/api/boards",
            {
                "name": BOARD_NAME,
                "columnCount": BOARD_COLUMN_COUNT,
                "isPublic": BOARD_PUBLIC,
            },
        )
        if not isinstance(result, dict) or not result.get("boardId"):
            raise RuntimeError("Homarr did not return boardId while creating board")
        board_id = str(result["boardId"])
        state[state_key] = board_id
        created_board = True
        log(f"created Homarr board {BOARD_NAME!r} as {board_id}")
    else:
        board_id = str(existing.get("id", ""))
        if not board_id:
            raise RuntimeError(f"Homarr board {BOARD_NAME!r} has no id")
        if not mapped_board_id:
            log(
                f"board {BOARD_NAME!r} already exists but is not managed by Nabla; "
                "leaving it unchanged to avoid duplicate items"
            )
            return False, 0
        if mapped_board_id != board_id:
            log(
                f"managed board mapping points to {mapped_board_id}, but Homarr "
                f"reports {board_id}; leaving the replacement board unchanged"
            )
            return False, 0

    added = 0
    for item in desired_items:
        nabla_id = str(item["id"])
        homarr_app_id = state.get(nabla_id)
        if not homarr_app_id:
            log(f"skipping board item {nabla_id}: Homarr app id is unavailable")
            continue
        item_state_key = board_item_state_key(nabla_id)
        if state.get(item_state_key):
            continue
        if DRY_RUN:
            log(
                f"would add {nabla_id} / {homarr_app_id} "
                f"to board {BOARD_NAME!r}"
            )
            continue
        result = request_json(
            "POST",
            "/api/boards/items",
            {
                "boardId": board_id,
                "kind": "app",
                "options": {"appId": homarr_app_id},
                "integrationIds": [],
            },
        )
        if not isinstance(result, dict) or not result.get("itemId"):
            raise RuntimeError(
                f"Homarr did not return itemId while adding {nabla_id} to board"
            )
        state[item_state_key] = str(result["itemId"])
        added += 1
        log(f"added {nabla_id} to Homarr board {BOARD_NAME!r}")

    return created_board, added


def main() -> int:
    if not API_KEY:
        log("HOMARR_API_KEY is not set; skipping reconciliation without failing the stack")
        return 0

    manifest = load_json(MANIFEST_PATH, {})
    if not isinstance(manifest, dict) or not isinstance(manifest.get("applications"), list):
        log(f"invalid manifest: {MANIFEST_PATH}")
        return 2

    desired_items = [
        item
        for item in manifest["applications"]
        if isinstance(item, dict) and item.get("syncEligible") is True and item.get("href")
    ]
    state_raw = load_json(STATE_PATH, {})
    state = state_raw if isinstance(state_raw, dict) else {}
    state = {str(key): str(value) for key, value in state.items()}

    apps = wait_for_homarr()
    created = updated = unchanged = 0

    for item in desired_items:
        nabla_id = str(item["id"])
        payload = desired_payload(item)
        existing = find_existing(payload, apps, state.get(nabla_id))

        if existing is None:
            if DRY_RUN:
                log(f"would create {nabla_id}: {payload['name']} -> {payload['href']}")
                continue
            created_app = request_json("POST", "/api/apps", payload)
            if not isinstance(created_app, dict) or not created_app.get("id"):
                raise RuntimeError(f"Homarr did not return an id while creating {nabla_id}")
            state[nabla_id] = str(created_app["id"])
            apps.append(created_app)
            created += 1
            log(f"created {nabla_id} as Homarr app {created_app['id']}")
            continue

        homarr_id = str(existing["id"])
        state[nabla_id] = homarr_id
        if not differs(existing, payload):
            unchanged += 1
            continue
        if DRY_RUN:
            log(f"would update {nabla_id} / {homarr_id}")
            continue
        request_json("PATCH", f"/api/apps/{homarr_id}", payload)
        updated += 1
        log(f"updated {nabla_id} / {homarr_id}")

    board_created, board_items_added = reconcile_board(state, desired_items)

    if not DRY_RUN:
        save_state(state)
    log(
        f"reconciliation complete: desired={len(desired_items)} created={created} "
        f"updated={updated} unchanged={unchanged} board_created={board_created} "
        f"board_items_added={board_items_added} dry_run={DRY_RUN}"
    )
    log("no Homarr applications, boards or board items were deleted")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        log(f"ERROR: {exc}")
        raise SystemExit(1) from exc
