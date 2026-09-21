"""Repository catalog helpers shared by local operator tools."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import yaml

from .model import ServiceIntent, normalize_service_intent


def load_catalog(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def app_directory(source_path: str) -> str | None:
    match = re.match(r"^apps/([^/]+)/", source_path)
    return match.group(1) if match else None


def _manual_compose_app(compose_path: Path, compose_services: set[str]) -> bool:
    """Return true only when every declared runtime service is manual-only."""

    if not compose_path.exists():
        return False

    payload = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
    services = payload.get("services")
    if not isinstance(services, dict):
        return False

    targets = sorted(compose_services)
    if not targets and len(services) == 1:
        targets = [str(next(iter(services)))]

    if not targets:
        return False

    for name in targets:
        service = services.get(name)
        if not isinstance(service, dict):
            return False
        profiles = service.get("profiles") or []
        if not isinstance(profiles, list) or "manual" not in profiles:
            return False
    return True


def declared_apps(catalog: dict[str, Any], *, root: Path) -> list[dict[str, Any]]:
    """Collapse logical services into repository application/runtime rows."""

    grouped: dict[str, dict[str, Any]] = {}
    for service in catalog.get("services", []):
        if not isinstance(service, dict):
            continue
        source_path = str(service.get("sourcePath") or "")
        app = app_directory(source_path)
        runtime = service.get("runtime") or {}
        if not app or runtime.get("provider") != "truenas-app":
            continue

        row = grouped.setdefault(
            app,
            {
                "app": app,
                "sourcePath": source_path,
                "serviceIds": [],
                "composeServices": set(),
                "explicitAppIds": set(),
                "statuses": set(),
                "monitoring": [],
            },
        )
        row["serviceIds"].append(str(service.get("id") or ""))
        compose_service = service.get("composeService")
        if compose_service:
            row["composeServices"].add(str(compose_service))
        row["statuses"].add(normalize_service_intent(service.get("status")).value)
        if runtime.get("appId"):
            row["explicitAppIds"].add(str(runtime["appId"]))
        if service.get("monitoring"):
            row["monitoring"].append(service["monitoring"])

    result: list[dict[str, Any]] = []
    for app, row in sorted(grouped.items()):
        statuses = sorted(row.pop("statuses"))
        row["status"] = statuses[0] if len(statuses) == 1 else None
        row["statusError"] = (
            None if len(statuses) == 1 else f"conflicting service statuses: {statuses}"
        )

        explicit = sorted(row.pop("explicitAppIds"))
        if len(explicit) > 1:
            row["runtimeId"] = None
            row["mappingError"] = f"conflicting runtime.appId values: {explicit}"
        else:
            row["runtimeId"] = explicit[0] if explicit else app
            row["mappingError"] = None

        compose_services = row.pop("composeServices")
        compose = root / row["sourcePath"]
        row["manual"] = _manual_compose_app(compose, compose_services)
        row["initializationEligible"] = (
            row["status"] == ServiceIntent.ACTIVE.value and not row["manual"]
        )
        result.append(row)

    return result
