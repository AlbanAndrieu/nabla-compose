#!/usr/bin/env python3
"""Read-only two-wave TrueNAS restart preparation from Catalog v2 and app.query.

No restarts, shell execution, credentials, or service state mutation.
Use an app.query snapshot captured separately from the TrueNAS appliance.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUNNING = {"RUNNING"}
SECRET_FILE = "/mnt/cpool/secrets/runtime/{app}/.env.secrets"


def plan(
    catalog: dict[str, Any],
    mappings: dict[str, Any],
    manifest: dict[str, Any],
    apps: list[dict[str, Any]],
    runtime_root: Path | None = None,
) -> dict[str, Any]:
    if catalog.get("catalogRevision") != mappings.get("catalogRevision"):
        raise ValueError("catalogRevision differs from the identity map")
    entities = {entity["entityRef"]: entity for entity in catalog["entities"]}
    by_compose: dict[str, set[str]] = defaultdict(set)
    for mapping in mappings["mappings"]:
        if mapping["sourceType"] != "compose":
            continue
        source = mapping["sourceId"]
        if not source.startswith("apps/") or "#services/" not in source:
            continue
        app_id = source.split("/", 2)[1]
        if mapping["entityRef"] not in entities:
            raise ValueError(f"unresolved entityRef in crosswalk: {mapping['entityRef']}")
        by_compose[app_id].add(mapping["entityRef"])

    secret_apps = {item["app"] for item in manifest["items"]}
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "catalogRevision": catalog["catalogRevision"],
        "mode": "read-only",
        "waveRunning": [],
        "waveOther": [],
        "blocked": [],
    }
    seen: set[str] = set()
    for app in sorted(apps, key=lambda item: str(item.get("name") or item.get("id") or "")):
        app_id = app.get("name") or app.get("id")
        if not isinstance(app_id, str) or not app_id:
            raise ValueError("TrueNAS app.query row lacks name/id")
        if app_id in seen:
            raise ValueError(f"duplicate TrueNAS app id: {app_id}")
        seen.add(app_id)
        state = str(app.get("state") or app.get("status") or "UNKNOWN").upper()
        refs = sorted(by_compose.get(app_id, []))
        prerequisites = sorted({
            ref for entity_ref in refs
            for ref in (entities[entity_ref].get("spec") or {}).get("dependsOn", [])
            if ref not in refs
        })
        missing = [ref for ref in prerequisites if ref not in entities]
        declared = {
            str((entities[ref].get("metadata") or {}).get("labels", {}).get(
                "albandrieu.com/operational-state", "active"
            ))
            for ref in refs
        }
        secret_manifest = app_id in secret_apps
        path = SECRET_FILE.format(app=app_id) if secret_manifest else None
        runtime_secret: str = "not-checked"
        if path is not None and runtime_root is not None:
            physical = runtime_root / path.lstrip("/")
            runtime_secret = "present" if physical.is_file() else "missing"
        entry = {
            "app": app_id,
            "observedState": state,
            "entityRefs": refs,
            "declaredStates": sorted(declared),
            "dependsOn": prerequisites,
            "vaultwardenManifest": secret_manifest,
            "runtimeSecretPath": path,
            "runtimeSecretFile": runtime_secret,
            "vaultwardenItemVerified": False,
        }
        if missing or (state == "RUNNING" and "disabled" in declared):
            entry["blockers"] = (
                [f"missing Backstage dependency: {x}" for x in missing]
                + (["running but declared disabled"] if "disabled" in declared else [])
            )
            result["blocked"].append(entry)
        elif state in RUNNING:
            result["waveRunning"].append(entry)
        else:
            result["waveOther"].append(entry)
    result["counts"] = {
        "running": len(result["waveRunning"]),
        "other": len(result["waveOther"]),
        "blocked": len(result["blocked"]),
        "unmapped": sum(not item["entityRefs"] for key in ("waveRunning", "waveOther")
                        for item in result[key]),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apps-json", type=Path, required=True,
                        help="TrueNAS app.query JSON array captured privately")
    parser.add_argument("--runtime-root", type=Path,
                        help="optional TrueNAS root mount: check only file existence")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    apps = json.loads(args.apps_json.read_text(encoding="utf-8"))
    if not isinstance(apps, list):
        raise ValueError("--apps-json must contain a TrueNAS app.query array")
    result = plan(
        json.loads((ROOT / "catalog/generated/entities.json").read_text()),
        json.loads((ROOT / "catalog/generated/identity-map.json").read_text()),
        json.loads((ROOT / "config/secrets/manifest.json").read_text()),
        apps,
        args.runtime_root,
    )
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
