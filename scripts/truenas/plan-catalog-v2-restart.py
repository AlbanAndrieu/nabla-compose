#!/usr/bin/env python3
"""Read-only restart preparation from Backstage v2 and sanitized TrueNAS app states.

Input app-query JSON must contain ONLY id/state, never unredacted app.query.
No TrueNAS mutation and no credential value reads. Use --check-host-secrets on
TrueNAS to stat the configured runtime files without logging their contents.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
from collections import defaultdict
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from nabla_ops.catalog_exports import load_backstage_entities  # noqa: E402
from nabla_ops.compose_paths import tracked_compose_paths  # noqa: E402


def stable_app_states(snapshot: Any) -> dict[str, str]:
    if not isinstance(snapshot, list):
        raise ValueError("sanitized app.query snapshot must be an array")
    states: dict[str, str] = {}
    for item in snapshot:
        if not isinstance(item, dict) or set(item) != {"id", "state"}:
            raise ValueError("snapshot must contain ONLY id and state per App")
        app, state = item["id"], item["state"]
        if not isinstance(app, str) or not app or not isinstance(state, str):
            raise ValueError("App id/state must be nonempty strings")
        if app in states:
            raise ValueError(f"duplicate TrueNAS App {app}")
        states[app] = state.upper()
    return states


def topo_waves(apps: set[str], edges: set[tuple[str, str]]) -> list[list[str]]:
    outgoing: dict[str, set[str]] = defaultdict(set)
    incoming = {app: 0 for app in apps}
    for prereq, target in sorted(edges):
        if prereq == target:
            continue
        if prereq not in apps or target not in apps:
            continue
        if target not in outgoing[prereq]:
            outgoing[prereq].add(target)
            incoming[target] += 1
    result: list[list[str]] = []
    waiting = dict(incoming)
    while waiting:
        ready = sorted(app for app, count in waiting.items() if count == 0)
        if not ready:
            raise ValueError("Backstage cross-app dependency cycle")
        result.append(ready)
        for app in ready:
            waiting.pop(app)
            for target in outgoing[app]:
                if target in waiting:
                    waiting[target] -= 1
    return result


def configured_secret_files(root: Path) -> dict[str, list[str]]:
    """Read native Compose env_file + secrets.file locations, not any value."""
    by_app: dict[str, set[str]] = defaultdict(set)
    for relative in tracked_compose_paths(root):
        if len(relative.parts) < 3 or relative.parts[0] != "apps":
            continue
        app = relative.parts[1]
        payload = yaml.safe_load((root / relative).read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            continue
        for service in (payload.get("services") or {}).values():
            if not isinstance(service, dict):
                continue
            for item in service.get("env_file") or []:
                value = item if isinstance(item, str) else item.get("path") if isinstance(item, dict) else None
                if isinstance(value, str) and value.endswith(".env.secrets"):
                    by_app[app].add(value)
            secrets = payload.get("secrets") or {}
            for secret in service.get("secrets") or []:
                key = secret if isinstance(secret, str) else secret.get("source") if isinstance(secret, dict) else None
                declaration = secrets.get(key) if isinstance(secrets, dict) else None
                value = declaration.get("file") if isinstance(declaration, dict) else None
                if isinstance(value, str) and value.endswith(".env.secrets"):
                    by_app[app].add(value)
    return {app: sorted(files) for app, files in by_app.items()}


def secret_file_posture(path: str) -> str:
    """Host-only metadata check, no opening contents, no chmod mutation."""
    if not os.path.isabs(path):
        return "non-absolute"
    try:
        info = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unreadable-metadata"
    if not stat.S_ISREG(info.st_mode):
        return "not-regular-file"
    if (info.st_mode & 0o077) or info.st_uid != 0:
        return "weak-permissions-or-ownership"
    return "present-root-only"


def build_plan(
    root: Path,
    snapshot: list[dict[str, str]],
    check_host_secrets: bool = False,
) -> dict[str, Any]:
    states = stable_app_states(snapshot)
    descriptors = [root / "catalog/catalog-info.yaml"]
    descriptors.extend(sorted((root / "apps").glob("*/catalog-info.yaml")))
    entities = load_backstage_entities(path for path in descriptors if path.is_file())
    refs = {ent["entityRef"]: ent for ent in entities}
    # Link to actual TrueNAS App through the repo's native, explicit Compose
    # entity-ref label. App directory is an app deployment unit, not a guessed
    # display-name alias.
    ref_apps: dict[str, set[str]] = defaultdict(set)
    app_states: dict[str, set[str]] = defaultdict(set)
    for relative in tracked_compose_paths(root):
        if len(relative.parts) < 3 or relative.parts[0] != "apps":
            continue
        app = relative.parts[1]
        payload = yaml.safe_load((root / relative).read_text(encoding="utf-8")) or {}
        for service in (payload.get("services") or {}).values():
            if not isinstance(service, dict):
                continue
            labels = service.get("labels") or {}
            if isinstance(labels, list):
                labels = dict(v.split("=", 1) for v in labels if isinstance(v, str) and "=" in v)
            if not isinstance(labels, dict):
                continue
            ref = labels.get("com.albandrieu.nabla.entity-ref")
            if not isinstance(ref, str):
                continue
            ref = ref.strip().lower()
            if ref not in refs:
                raise ValueError(f"{relative}: unknown Backstage entity {ref}")
            ref_apps[ref].add(app)
            labels = refs[ref].get("metadata", {}).get("labels", {})
            state = labels.get("albandrieu.com/operational-state", "active")
            app_states[app].add(state)
    edges: set[tuple[str, str]] = set()
    for ref, apps in ref_apps.items():
        depends = refs[ref].get("spec", {}).get("dependsOn", [])
        for target in depends if isinstance(depends, list) else []:
            for app in apps:
                for prerequisite in ref_apps.get(target, set()):
                    if prerequisite != app:
                        edges.add((prerequisite, app))
    secrets = configured_secret_files(root)
    manifest = json.loads((root / "config/secrets/manifest.json").read_text(encoding="utf-8"))
    vaulted = {item["app"]: item["item"] for item in manifest["items"]}
    rows: list[dict[str, Any]] = []
    for app, state in sorted(states.items()):
        paths = secrets.get(app, [])
        status = sorted(app_states.get(app, []))
        declared = bool(status)
        blocked = status and set(status) <= {"planned", "disabled"}
        dependencies = sorted(
            dep for dep, target in edges if target == app and dep in states
        )
        secret_files = [
            {"path": path, "status": secret_file_posture(path)
             if check_host_secrets else "not-checked"} for path in paths
        ]
        blockers = []
        if blocked:
            blockers.append("planned-or-disabled")
        if state in {"CRASHED", "ERROR", "DEPLOYING"}:
            blockers.append("runtime-diagnostic-required")
        # A RUNNING dependent must not be redeployed before a non-running
        # prerequisite. We keep it in stage A for visibility, but HOLD it.
        if state == "RUNNING" and any(states[dep] != "RUNNING" for dep in dependencies):
            blockers.append("dependency-not-running")
        if check_host_secrets and any(
            item["status"] != "present-root-only" for item in secret_files
        ):
            blockers.append("runtime-secrets-not-ready")
        rows.append({
            "appId": app,
            "currentState": state,
            "stage": "running-first" if state == "RUNNING" else "remaining",
            "action": ("hold" if blockers else "redeploy" if state == "RUNNING" else "start"),
            "blockers": blockers,
            "catalogMapped": declared,
            "declaredStates": status,
            "vaultwardenItem": vaulted.get(app),
            "vaultwardenValidation": "not-checked",
            "runtimeSecretFiles": secret_files,
            "dependencies": dependencies,
        })
    stage_order: dict[str, list[list[str]]] = {}
    for stage in ("running-first", "remaining"):
        subset = {item["appId"] for item in rows if item["stage"] == stage}
        stage_order[stage] = topo_waves(subset, edges)
    return {
        "schemaVersion": 1,
        "source": "backstage-compose-truenas-app-query",
        "readOnly": True,
        "stages": stage_order,
        "apps": rows,
        "notes": [
            "Snapshot state is not proof of runtime health.",
            "RUNNING first; later waves may be blocked by a non-running prerequisite.",
            "No app restart happens in this planner.",
            "Secrets presence/permissions do not confirm Vaultwarden content or validity.",
            "CRASHED/ERROR/DEPLOYING and planned/disabled Apps require operator review.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--app-query-json", type=Path, required=True)
    parser.add_argument("--check-host-secrets", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    snapshot = json.loads(args.app_query_json.read_text(encoding="utf-8"))
    report = build_plan(args.root, snapshot, args.check_host_secrets)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
