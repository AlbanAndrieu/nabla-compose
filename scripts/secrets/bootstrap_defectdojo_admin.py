#!/usr/bin/env python3
"""Generate a unique DefectDojo bootstrap login directly into its Vaultwarden item.

Provisioning is safe without probing the app DB. For a running instance use a distinct,
controlled Django password rotation and then reconcile Vaultwarden.
Never prints credentials, writes plaintext files or edits other secrets.
"""
from __future__ import annotations

import argparse
import os
import secrets

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--fresh-initializer-confirmed", action="store_true", help="legacy compatibility; no live DefectDojo DB probing")
    args = p.parse_args()
    if args.check == args.apply:
        p.error("choose --check or --apply")
    if args.check:
        print("CHECK: Vaultwarden existing exact item; generate before first initializer only")
        return 0
    from import_env_to_bitwarden import create_item, edit_item, exact_items, sync_after_write
    from render_from_bitwarden import BitwardenClient, SecretsError, load_manifest
    manifest = load_manifest(ROOT / "config/secrets/manifest.json")
    spec = next(item for item in manifest["items"] if item["app"] == "defectdojo")
    assert {"DD_ADMIN_USER", "DD_ADMIN_PASSWORD"} <= {s["env"] for s in spec["secrets"]}
    if os.geteuid() == 0:
        p.error("only an unlocked non-root Vaultwarden operator may apply")
    client = BitwardenClient(session=os.environ.get("BW_SESSION", ""), server=manifest["server"])
    client.verify()
    folder = manifest["folder"]
    client.verify_folder(folder["id"], folder["name"])
    matches = exact_items(client, name=spec["item"], folder_id=folder["id"])
    if len(matches) > 1:
        raise SecretsError("duplicate DefectDojo Vaultwarden items; refusing write")
    item = matches[0] if matches else None
    login = (item or {}).get("login") or {}
    if login.get("password"):
        if login.get("username") != "nabla":
            raise SecretsError("existing login differs from requested nabla account; no rotation")
        print("EXISTS: DefectDojo nabla credential already in Vaultwarden; unchanged")
        return 0
    if login.get("username") not in {"admin", "nabla", "homelab:defectdojo", None, ""}:
        raise SecretsError("unexpected existing username; manual reconciliation required")
    payload = dict(item or {})
    payload.update(type=1, name=spec["item"], folderId=folder["id"])
    payload["login"] = {
        **login,
        "username": "nabla",
        "password": secrets.token_urlsafe(48),
        "uris": login.get("uris") or [{"uri": "https://defectdojo.int.albandrieu.com"}],
    }
    payload.setdefault("fields", [])
    if item:
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise SecretsError("existing Vaultwarden item has no ID")
        edit_item(client, item_id=item_id, payload=payload)
    else:
        create_item(client, payload)
    if not sync_after_write(client, [spec["item"]]):
        raise SecretsError("Vaultwarden write accepted but sync unverified; do not rerun")
    print("OK: generated DefectDojo nabla credential in Vaultwarden; no secret printed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
