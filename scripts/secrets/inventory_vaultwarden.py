#!/usr/bin/env python3
"""Inventory Vaultwarden against the Nabla manifest without exposing secret values.

Modes are read-only. Never print raw bw JSON, custom fields, passwords or sessions.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

DEFAULT_MANIFEST = Path("config/secrets/manifest.json")


def inventory(manifest: dict, folders: list[dict], items: list[dict]) -> tuple[list[dict], int]:
    expected_folder = manifest["folder"]
    matching = [
        folder for folder in folders
        if folder.get("id") == expected_folder["id"]
        and folder.get("name") == expected_folder["name"]
    ]
    folder_ok = len(matching) == 1
    results = []
    missing = 0
    for spec in manifest["items"]:
        matches = [
            item for item in items
            if item.get("name") == spec["item"]
            and item.get("folderId") == expected_folder["id"]
        ]
        count = len(matches)
        status = "present" if folder_ok and count == 1 else ("duplicate" if count > 1 else "missing")
        missing += status != "present"
        # Deliberately exclude item JSON, IDs, fields, usernames and URLs.
        results.append({"app": spec["app"], "status": status})
    return results, missing + (not folder_ok)


def bw_json(*args: str, session: str) -> list[dict]:
    result = subprocess.run(
        ["bw", *args, "--session", session],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        # stderr may contain sensitive server data; do not echo it.
        raise RuntimeError(f"bw {args[0]} failed; exit={result.returncode}")
    data = json.loads(result.stdout)
    if not isinstance(data, list):
        raise RuntimeError("unexpected Bitwarden response type")
    return [x for x in data if isinstance(x, dict)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--app", help="limit report to this declared app")
    parser.add_argument("--json", action="store_true", help="metadata-only JSON report")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    expected = {x["app"] for x in manifest["items"]}
    if args.app and args.app not in expected:
        parser.error("unknown application")

    server = subprocess.run(
        ["bw", "config", "server"], capture_output=True, text=True, check=False, timeout=10
    )
    if server.returncode or server.stdout.strip().rstrip("/") != manifest["server"].rstrip("/"):
        print("ERROR: Bitwarden CLI base server differs from manifest", file=sys.stderr)
        return 2

    session = os.environ.get("BW_SESSION", "")
    if not session:
        print("ERROR: BW_SESSION is missing; unlock the vault as unprivileged operator", file=sys.stderr)
        return 2

    status = subprocess.run(
        ["bw", "status"], capture_output=True, text=True, check=False, timeout=10,
        env={**os.environ, "BW_SESSION": session},
    )
    try:
        state = json.loads(status.stdout)
    except json.JSONDecodeError:
        state = {}
    if status.returncode or state.get("status") != "unlocked":
        print("ERROR: Bitwarden CLI vault is not unlocked", file=sys.stderr)
        return 2

    folders = bw_json("list", "folders", session=session)
    items = bw_json("list", "items", session=session)
    rows, failures = inventory(manifest, folders, items)
    if args.app:
        rows = [row for row in rows if row["app"] == args.app]
        failures = sum(row["status"] != "present" for row in rows)
    if args.json:
        print(json.dumps({"folder_verified": any(
            f.get("id") == manifest["folder"]["id"] and f.get("name") == manifest["folder"]["name"]
            for f in folders
        ), "apps": rows}, indent=2))
    else:
        print("Vaultwarden manifest inventory (metadata only):")
        for row in rows:
            print(f"{row['app']}: {row['status']}")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired, ValueError, RuntimeError) as exc:
        print(f"ERROR: inventory failed ({type(exc).__name__}); no secret data emitted", file=sys.stderr)
        raise SystemExit(2) from None
