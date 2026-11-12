#!/usr/bin/env python3
"""Reconcile generated Nabla applications and dashboard into Homarr."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = os.getenv("HOMARR_BASE_URL", "http://homarr:7575").rstrip("/")
# HOMARR_API_KEY is canonical (config/secrets/manifest.json). Runtime files
# materialised before the 06/11 migration still carry HOMARR_API_TOKEN.
API_KEY = (os.getenv("HOMARR_API_KEY") or os.getenv("HOMARR_API_TOKEN") or "").strip()
LEGACY_KEY_NAME = not os.getenv("HOMARR_API_KEY") and bool(os.getenv("HOMARR_API_TOKEN"))
MANIFEST_PATH = Path(os.getenv("HOMARR_MANIFEST", "/config/nabla/apps.json"))
BOARDS_PATH = Path(os.getenv("HOMARR_BOARDS_CONFIG", "/config/boards.json"))
DRY_RUN = os.getenv("HOMARR_SYNC_DRY_RUN", "false").lower() in {"1", "true", "yes", "on"}
# 3 min: on 2026-11-11 Homarr answered 502 for more than 60 s after app.redeploy.
MAX_ATTEMPTS = int(os.getenv("HOMARR_SYNC_ATTEMPTS", "60"))
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
# Board names, columns, visibility and members are declared in BOARDS_PATH.
# LiteLLM virtual key registered by scripts/truenas/register-litellm-app-keys.py.
ASSISTANT_API_KEY = os.getenv("HOMARR_ASSISTANT_API_KEY", "").strip()
ASSISTANT_BASE_URL = os.getenv("HOMARR_ASSISTANT_BASE_URL", "http://172.17.0.24:4000/v1")
ASSISTANT_MODEL = os.getenv("HOMARR_ASSISTANT_MODEL", "qwen")
MOBILE_COLUMNS = 3
WIDGET_WIDTH = 3
WIDGET_HEIGHT = 2


class AuthRejected(RuntimeError):
    """Homarr refused the API key: retrying cannot help."""


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
        error = AuthRejected if exc.code in {401, 403} else RuntimeError
        raise error(
            f"Homarr API {method} {path} returned {exc.code}: {body[:400]}"
        ) from exc
    # A read timeout raises TimeoutError, not URLError: on a cold boot it ended the wait loop.
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(
            f"Homarr API {method} {path} unavailable: {getattr(exc, 'reason', exc)}"
        ) from exc
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def load_json(path: Path, fallback: object) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def wait_for_homarr() -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            apps = request_json("GET", "/api/apps")
            if isinstance(apps, list):
                return [app for app in apps if isinstance(app, dict)]
            raise RuntimeError("Homarr /api/apps did not return an array")
        except AuthRejected:
            raise
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
        # Homarr v2.6 requires the key (URL, "" or null): pinging the app URL shows its status.
        "pingUrl": str(item["href"]),
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
    for key in ("name", "description", "iconUrl", "href", "pingUrl"):
        if existing.get(key) != desired.get(key):
            return True
    return False


def board_content(
    board_id: str,
    columns: int,
    widgets: list[dict[str, Any]],
    groups: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Lay out the widgets, then one titled section per group of Homarr app ids."""
    layouts = [
        {"id": f"{board_id}-base", "name": "Base", "columnCount": columns, "breakpoint": 768, "role": "base"},
        {"id": f"{board_id}-mobile", "name": "Mobile", "columnCount": MOBILE_COLUMNS, "breakpoint": 0, "role": "mobile"},
    ]
    root = f"{board_id}-root"
    sections: list[dict[str, Any]] = [{"id": root, "kind": "empty", "xOffset": 0, "yOffset": 0}]
    items: list[dict[str, Any]] = []
    next_row: dict[str, int] = {}
    for layout in layouts:
        per_row = max(layout["columnCount"] // WIDGET_WIDTH, 1)
        next_row[layout["id"]] = -(-len(widgets) // per_row) * WIDGET_HEIGHT
    for index, widget in enumerate(widgets):
        placements = []
        for layout in layouts:
            per_row = max(layout["columnCount"] // WIDGET_WIDTH, 1)
            placements.append({
                "layoutId": layout["id"], "sectionId": root,
                "xOffset": index % per_row * WIDGET_WIDTH, "yOffset": index // per_row * WIDGET_HEIGHT,
                "width": min(WIDGET_WIDTH, layout["columnCount"]), "height": WIDGET_HEIGHT,
            })
        items.append({
            "id": f"{board_id}-widget-{index}", "kind": str(widget["kind"]),
            "options": dict(widget.get("options", {})),
            "integrationIds": [], "advancedOptions": {}, "layouts": placements,
        })
    for group, app_ids in sorted(groups.items()):
        section = f"{board_id}-group-{group}"
        section_layouts = []
        for layout in layouts:
            # One extra row holds the section title.
            height = -(-len(app_ids) // layout["columnCount"]) + 1
            section_layouts.append({
                "layoutId": layout["id"], "parentSectionId": root, "xOffset": 0,
                "yOffset": next_row[layout["id"]], "width": layout["columnCount"], "height": height,
            })
            next_row[layout["id"]] += height
        sections.append({
            "id": section, "kind": "container", "collapsed": False,
            "options": {"title": group.capitalize()}, "layouts": section_layouts,
        })
        for index, app_id in enumerate(app_ids):
            items.append({
                "id": f"{section}-{app_id}", "kind": "app",
                "options": {"appId": app_id, "openInNewTab": True, "showTitle": True},
                "integrationIds": [], "advancedOptions": {},
                "layouts": [
                    {
                        "layoutId": layout["id"], "sectionId": section,
                        "xOffset": index % layout["columnCount"], "yOffset": index // layout["columnCount"],
                        "width": 1, "height": 1,
                    }
                    for layout in layouts
                ],
            })
    return layouts, {"sections": sections, "items": items}


def reconcile_board(
    state: dict[str, str],
    desired_items: list[dict[str, Any]],
) -> tuple[bool, int]:
    """Write the boards declared in boards.json in full; code owns them.

    Boards are matched by name: a missing board is created, then its layouts
    and whole content (widgets, one section per application group) are
    replaced, so manual edits to these boards do not survive a sync. Other
    boards are never touched.
    """
    if not BOARD_SYNC_ENABLED:
        return False, 0
    definitions = load_json(BOARDS_PATH, {})
    if not isinstance(definitions, dict) or definitions.get("version") != 1:
        raise ValueError("Homarr boards configuration requires version: 1")
    boards_config = definitions.get("boards")
    if not isinstance(boards_config, list) or not boards_config:
        raise ValueError("boards must be a nonempty array")
    remote = request_json("GET", "/api/boards")
    if not isinstance(remote, list):
        raise RuntimeError("Homarr /api/boards response is not an array")
    created = False
    written = 0
    eligible = {str(item["id"]): item for item in desired_items}
    for config in boards_config:
        if not isinstance(config, dict):
            raise ValueError("Invalid board configuration")
        name = str(config["name"])
        selected = config.get("applications", [])
        if selected == "*":
            selected = sorted(eligible)
        if not isinstance(selected, list):
            raise ValueError(f"invalid applications for board {name}")
        selected = list(dict.fromkeys(str(nabla_id) for nabla_id in selected))
        for nabla_id in selected:
            if nabla_id not in eligible:
                raise ValueError(f"unknown or ineligible application {nabla_id}")
        widgets = config.get("widgets", [])
        if not isinstance(widgets, list) or not all(isinstance(w, dict) and w.get("kind") for w in widgets):
            raise ValueError(f"invalid widgets for board {name}")
        matches = [b for b in remote if isinstance(b, dict) and b.get("name") == name]
        if len(matches) > 1:
            raise RuntimeError(f"ambiguous board name: {name}")
        if DRY_RUN:
            log(f"would write board {name}: {len(selected)} applications, {len(widgets)} widgets")
            continue
        if matches:
            board = matches[0]
        else:
            result = request_json("POST", "/api/boards", {
                "name": name,
                "columnCount": int(config.get("columns", 12)),
                "isPublic": bool(config.get("public", False)),
            })
            if not isinstance(result, dict) or not result.get("boardId"):
                raise RuntimeError(f"missing boardId for {name}")
            board = {"id": result["boardId"]}
            created = True
        board_id = str(board["id"])
        groups: dict[str, list[str]] = {}
        for nabla_id in selected:
            if state.get(nabla_id):
                group = str(eligible[nabla_id].get("group") or "other")
                groups.setdefault(group, []).append(state[nabla_id])
        layouts, content = board_content(board_id, int(config.get("columns", 12)), widgets, groups)
        # Content refers to these layout ids; both PUTs replace what the board held.
        request_json("PUT", f"/api/boards/{board_id}/layouts", {"layouts": layouts})
        request_json("PUT", f"/api/boards/{board_id}/content", content)
        written += len(content["items"])
        if config.get("home") is True:
            for flag, path in (("isHome", "home"), ("isMobileHome", "mobile-home")):
                if not board.get(flag):
                    request_json("PATCH", f"/api/boards/{board_id}/{path}")
    return created, written


def reconcile_assistant() -> str:
    """Point the Homarr assistant at LiteLLM as a custom OpenAI-compatible provider."""
    if not ASSISTANT_API_KEY:
        return "skipped_no_key"
    if DRY_RUN:
        log(f"would connect the assistant to {ASSISTANT_BASE_URL} model {ASSISTANT_MODEL}")
        return "dry_run"
    # No REST endpoint for the assistant: tRPC (superjson body), admin API key required.
    request_json("POST", "/api/trpc/assistant.updateConnection", {"json": {
        "provider": "custom",
        "baseUrl": ASSISTANT_BASE_URL,
        "modelDiscoveryPath": "/models",
        "apiKey": ASSISTANT_API_KEY,
    }})
    request_json("POST", "/api/trpc/assistant.updateConfiguration", {"json": {
        "enabled": True,
        "modelId": ASSISTANT_MODEL,
        "webSearchEnabled": False,
    }})
    return "connected"


def main() -> int:
    if not API_KEY:
        # A one-shot job exiting non-zero marks the whole TrueNAS App CRASHED
        # although the Homarr UI is healthy. Report the skipped reconciliation
        # loudly and exit 0; the gate is the SKIPPED marker, not the App state.
        log("RECONCILE_SKIPPED: HOMARR_API_KEY is not set; Homarr UI unaffected")
        return 0
    if LEGACY_KEY_NAME:
        log("WARNING: using legacy HOMARR_API_TOKEN; rematerialise HOMARR_API_KEY from Vaultwarden")

    manifest = load_json(MANIFEST_PATH, {})
    if not isinstance(manifest, dict) or not isinstance(manifest.get("applications"), list):
        log(f"invalid manifest: {MANIFEST_PATH}")
        return 2

    desired_items = [
        item
        for item in manifest["applications"]
        if isinstance(item, dict) and item.get("syncEligible") is True and item.get("href")
    ]
    state: dict[str, str] = {}

    try:
        apps = wait_for_homarr()
    except AuthRejected as exc:
        # Same contract as a missing key: a revoked key must not mark the App CRASHED.
        log(f"RECONCILE_SKIPPED: Homarr rejected the API key; rematerialise HOMARR_API_KEY ({exc})")
        return 0
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

    board_created, board_items = reconcile_board(state, desired_items)
    try:
        assistant = reconcile_assistant()
    except RuntimeError as exc:
        # Status line only: an error body could echo the request.
        assistant = "failed"
        log(f"ASSISTANT_RECONCILE_FAILED: {str(exc).split(':', 1)[0]}")

    log(
        f"reconciliation complete: desired={len(desired_items)} created={created} "
        f"updated={updated} unchanged={unchanged} board_created={board_created} "
        f"board_items={board_items} assistant={assistant} dry_run={DRY_RUN}"
    )
    log("no Homarr applications or boards were deleted; code-managed board content was replaced")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        log(f"ERROR: {exc}")
        raise SystemExit(1) from exc
