#!/usr/bin/env python3
"""Reconcile generated Nabla applications into Homarr without deleting user apps."""

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
        raise RuntimeError(f"Homarr API {method} {path} returned {exc.code}: {body[:400]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Homarr API {method} {path} unavailable: {exc.reason}") from exc
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
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
        if app.get("name") == desired.get("name") and app.get("href") == desired.get("href")
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

    if not DRY_RUN:
        save_state(state)
    log(
        f"reconciliation complete: desired={len(desired_items)} created={created} "
        f"updated={updated} unchanged={unchanged} dry_run={DRY_RUN}"
    )
    log("no Homarr applications were deleted")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        log(f"ERROR: {exc}")
        raise SystemExit(1) from exc
