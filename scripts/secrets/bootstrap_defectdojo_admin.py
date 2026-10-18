#!/usr/bin/env python3
"""Generate a unique DefectDojo bootstrap login directly into its Vaultwarden item.

Safe only BEFORE first initializer. For a running instance, use a distinct,
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
    p.add_argument("--fresh-initializer-confirmed", action="store_true")
    args = p.parse_args()
    if args.check == args.apply:
        p.error("choose --check or --apply")
    if args.check:
        print("CHECK: Vaultwarden existing exact item; generate before first initializer only")
        return 0
    from import_env_to_bitwarden import edit_item, sync_after_write
    from render_from_bitwarden import BitwardenClient, SecretsError, load_manifest
    manifest = load_manifest(ROOT / "config/secrets/manifest.json")
    spec = next(item for item in manifest["items"] if item["app"] == "defectdojo")
    assert {"DD_ADMIN_USER", "DD_ADMIN_PASSWORD"} <= {s["env"] for s in spec["secrets"]}
    if os.geteuid() == 0 or not args.fresh_initializer_confirmed:
        p.error("unprivileged user and --fresh-initializer-confirmed required")
    client = BitwardenClient(session=os.environ.get("BW_SESSION", ""), server=manifest["server"])
    client.verify()
    folder = manifest["folder"]
    client.verify_folder(folder["id"], folder["name"])
    item = client.get_exact_item(spec["item"], folder["id"])
    if (item.get("login") or {}).get("password"):
        raise SecretsError("existing DefectDojo login already has a password; refuse rotation")
    if (item.get("login") or {}).get("username") not in {"admin", "homelab:defectdojo", None, ""}:
        raise SecretsError("unexpected existing username; manual reconciliation required")
    payload = dict(item)
    payload["login"] = dict(item.get("login") or {})
    payload["login"]["username"] = "admin"
    payload["login"]["password"] = secrets.token_urlsafe(48)
    edit_item(client, item_id=str(item["id"]), payload=payload)
    if not sync_after_write(client, [spec["item"]]):
        raise SecretsError("Vaultwarden changed but sync unverified; do not rerun")
    print("OK: generated DefectDojo admin credential in Vaultwarden; no secret printed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
