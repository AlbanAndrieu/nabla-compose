#!/usr/bin/env python3
"""Fail-closed, value-blind migration receipt for Vaultwarden → TrueNAS files.

--check reads only Git metadata. --verify uses an operator's unlocked Bitwarden
CLI cache and compares rendered values against root-owned 0600 runtime files.
It never edits Vaultwarden, never installs runtime files, and cannot attest
that a running container has reloaded the values. Never print child output.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config/secrets/manifest.json"
INVENTORY = ROOT / "scripts/secrets/inventory_vaultwarden.py"
MATERIALIZE = ROOT / "scripts/secrets/materialize_runtime.py"


def manifest_summary(manifest: dict) -> dict:
    items = manifest.get("items")
    if not isinstance(items, list):
        raise ValueError("invalid items")
    names = [item.get("app") for item in items if isinstance(item, dict)]
    if len(names) != len(items) or any(not isinstance(n, str) for n in names):
        raise ValueError("invalid app name")
    if len(set(names)) != len(names):
        raise ValueError("duplicate app declaration")
    fields = [entry.get("secrets") for entry in items]
    if any(not isinstance(s, list) or not s for s in fields):
        raise ValueError("invalid secret mappings")
    if not isinstance(manifest.get("bootstrap"), list):
        raise ValueError("invalid bootstrap")
    return {
        "declared_apps": len(items),
        "declared_fields": sum(len(group) for group in fields),
        "bootstrap_entries": len(manifest["bootstrap"]),
    }


def safe_run(argv: list[str], timeout: int) -> tuple[int, str]:
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 2, ""
    # stderr may include a shell/credential value. Never propagate it.
    return result.returncode, result.stdout


def verify(manifest: dict, selection: list[str]) -> list[dict]:
    if os.geteuid() == 0 or not os.environ.get("BW_SESSION"):
        raise RuntimeError("requires a non-root operator with an unlocked BW_SESSION")
    sudo_rc, _ = safe_run(["sudo", "-n", "true"], 10)
    if sudo_rc:
        raise RuntimeError("passwordless sudo verification unavailable")
    rc, payload = safe_run(
        [sys.executable, str(INVENTORY), "--json", "--timeout-seconds", "90"], 210
    )
    try:
        inventory = json.loads(payload)
    except (ValueError, TypeError):
        raise RuntimeError("metadata inventory unavailable") from None
    if rc not in (0, 1) or inventory.get("folder_verified") is not True:
        raise RuntimeError("expected Vaultwarden folder not verified")
    observed = {row.get("app"): row.get("status")
                for row in inventory.get("apps", [])
                if isinstance(row, dict)}
    rows = []
    for spec in manifest["items"]:
        app = spec["app"]
        if app not in selection:
            continue
        vault = observed.get(app, "unverified")
        result = "UNVERIFIED"
        if vault == "present":
            parity_rc, _ = safe_run(
                [sys.executable, str(MATERIALIZE), "--app", app, "--verify"], 180
            )
            result = "FILE_PARITY_VERIFIED" if parity_rc == 0 else "UNVERIFIED"
        rows.append({
            "app": app,
            "declared_fields": len(spec["secrets"]),
            "vault_item": vault if vault in ("present", "missing", "duplicate") else "unverified",
            "runtime_file": result,
            "container_loaded": "NOT_VERIFIED",
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="offline manifest audit")
    group.add_argument("--verify", action="store_true", help="read-only operator parity check")
    parser.add_argument("--app", help="restrict read-only verification to one app")
    args = parser.parse_args()
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        result = manifest_summary(manifest)
    except (OSError, ValueError, KeyError, TypeError):
        print('{"status":"UNVERIFIED","reason":"INVALID_MANIFEST"}')
        return 2
    known = {item["app"] for item in manifest["items"]}
    if args.app and args.app not in known:
        parser.error("unknown app")
    report = {
        "schema": "nabla-vaultwarden-migration-receipt/v1",
        "source": "manifest_only" if args.check else "bitwarden_cli_cache",
        "status": "NOT_VERIFIED",
        **result,
    }
    if args.verify:
        try:
            rows = verify(manifest, [args.app] if args.app else sorted(known))
        except RuntimeError:
            print(json.dumps({**report, "reason": "OPERATOR_PARITY_UNAVAILABLE"},
                             sort_keys=True))
            return 2
        report["apps"] = rows
        report["file_parity_verified_apps"] = sum(
            row["runtime_file"] == "FILE_PARITY_VERIFIED" for row in rows
        )
        report["file_parity_verified_fields"] = sum(
            row["declared_fields"] for row in rows
            if row["runtime_file"] == "FILE_PARITY_VERIFIED"
        )
        report["status"] = (
            "FILE_PARITY_VERIFIED_NOT_CONTAINER_LOADED"
            if rows and all(row["runtime_file"] == "FILE_PARITY_VERIFIED" for row in rows)
            else "PARTIAL_OR_UNVERIFIED"
        )
    print(json.dumps(report, sort_keys=True))
    if args.check:
        return 0
    return 0 if report["status"] == "FILE_PARITY_VERIFIED_NOT_CONTAINER_LOADED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
