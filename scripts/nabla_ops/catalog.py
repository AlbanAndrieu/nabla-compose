"""Repository catalog helpers shared by local operator tools."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .model import ServiceIntent, normalize_service_intent


def load_catalog(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def app_directory(source_path: str) -> str | None:
    match = re.match(r"^apps/([^/]+)/", source_path)
    return match.group(1) if match else None


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
                "explicitAppIds": set(),
                "statuses": set(),
                "monitoring": [],
            },
        )
        row["serviceIds"].append(str(service.get("id") or ""))
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

        compose = root / row["sourcePath"]
        text = compose.read_text(encoding="utf-8") if compose.exists() else ""
        row["manual"] = bool(
            re.search(r"(?m)^\\s*profiles:\\s*$", text)
            and re.search(r"(?m)^\\s*-\\s*manual\\s*$", text)
        )
        row["initializationEligible"] = (
            row["status"] == ServiceIntent.ACTIVE.value and not row["manual"]
        )
        result.append(row)

    return result
