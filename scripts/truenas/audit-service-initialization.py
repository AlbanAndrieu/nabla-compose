#!/usr/bin/env python3
"""Audit declared repository Apps against live TrueNAS initialization state.

The command is read-only. It does not read secret values and never mutates
TrueNAS, Docker, Vaultwarden, datasets or runtime files.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog" / "services.json"
MANIFEST = ROOT / "config" / "secrets" / "manifest.json"

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "secrets"))
from nabla_ops import declared_apps, load_catalog  # noqa: E402
import audit_consumers  # noqa: E402


def live_apps() -> dict[str, dict[str, Any]]:
    try:
        result = subprocess.run(
            ["midclt", "call", "app.query"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise SystemExit("error: midclt is required; run this audit on TrueNAS") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"error: app.query failed: {(exc.stderr or '').strip() or exc.returncode}"
        ) from exc

    payload = json.loads(result.stdout)
    return {
        str(app["id"]): app
        for app in payload
        if isinstance(app, dict) and isinstance(app.get("id"), str)
    }


def canonical_secret_state(app: str) -> dict[str, Any]:
    path = Path(f"/mnt/cpool/secrets/runtime/{app}/.env.secrets")
    if not path.exists():
        return {"path": str(path), "present": False, "metadata": None}
    stat_result = path.stat()
    return {
        "path": str(path),
        "present": path.is_file() and not path.is_symlink() and stat_result.st_size > 0,
        "metadata": {
            "uid": stat_result.st_uid,
            "gid": stat_result.st_gid,
            "mode": f"{stat_result.st_mode & 0o777:03o}",
            "size": stat_result.st_size,
        },
    }


def by_app(entries: list[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for entry in entries:
        app = entry.split("|", 1)[0]
        result.setdefault(app, []).append(entry)
    return result


def recommend(row: dict[str, Any]) -> str:
    if row.get("statusError"):
        return "fix-service-status"
    if row.get("status", "active") == "disabled":
        return "disabled"
    if row.get("status", "active") == "planned":
        return "planned"
    if row["mappingError"]:
        return "fix-runtime-id"
    if row["manual"]:
        return "manual-job"
    if row["state"] == "MISSING":
        if row["unmanagedSecretVariables"] or row["legacyEnvFiles"]:
            return "secrets-first"
        if row["manifestManaged"] and not row["canonicalSecret"]["present"]:
            return "materialize-then-deploy"
        return "deploy"
    if row["state"] in {"CRASHED", "ERROR"}:
        return "diagnose-before-reconcile"
    if row["legacyEnvFiles"] or row["unmanagedSecretVariables"]:
        return "migrate-secrets"
    if row["manifestManaged"] and not row["canonicalSecret"]["present"]:
        return "materialize-secret"
    if row["insecureDefaults"]:
        return "remove-insecure-default"
    return "verify-runtime"


def build_report() -> list[dict[str, Any]]:
    catalog = load_catalog(CATALOG)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    static = audit_consumers.scan(ROOT, manifest)
    live = live_apps()
    managed_apps = {
        str(item["app"])
        for item in manifest.get("items", [])
        if isinstance(item, dict) and isinstance(item.get("app"), str)
    }

    legacy = by_app(static["legacyEnvFiles"])
    unmanaged = by_app(static["unmanagedSecretVariables"])
    insecure = by_app(static["insecureDefaults"])
    special = by_app(static["specialHostSecretFiles"])
    canonical_missing = by_app(static["canonicalRuntimeWithoutManifest"])

    rows: list[dict[str, Any]] = []
    for declared in declared_apps(catalog, root=ROOT):
        app = declared["app"]
        runtime_id = declared["runtimeId"]
        live_row = live.get(runtime_id or "", {})
        state = str(live_row.get("state") or "MISSING")
        row = {
            **declared,
            "state": state,
            "manifestManaged": app in managed_apps,
            "canonicalSecret": canonical_secret_state(app),
            "legacyEnvFiles": legacy.get(app, []),
            "unmanagedSecretVariables": unmanaged.get(app, []),
            "insecureDefaults": insecure.get(app, []),
            "specialHostSecretFiles": special.get(app, []),
            "canonicalRuntimeWithoutManifest": canonical_missing.get(app, []),
        }
        row["action"] = recommend(row)
        rows.append(row)
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--missing-only", action="store_true")
    parser.add_argument("--action", help="filter by recommended action")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = build_report()
    if args.missing_only:
        rows = [row for row in rows if row["state"] == "MISSING"]
    if args.action:
        rows = [row for row in rows if row["action"] == args.action]

    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0

    print(
        f"{'APP':24} {'TRUENAS':24} {'STATE':11} {'SECRETS':10} {'ACTION'}"
    )
    for row in rows:
        secret_state = "managed" if row["manifestManaged"] else "unmanaged"
        if row["legacyEnvFiles"]:
            secret_state += "/legacy"
        print(
            f"{row['app'][:24]:24} "
            f"{str(row['runtimeId'] or '-')[:24]:24} "
            f"{row['state'][:11]:11} "
            f"{secret_state[:10]:10} "
            f"{row['action']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
