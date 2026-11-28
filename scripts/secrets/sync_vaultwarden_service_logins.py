#!/usr/bin/env python3
"""Add each service's UI URLs, and its UI login when the item already stores it, to Vaultwarden.

For every manifest item `nabla/prod/<app>` in the TrueNAS folder:
- the login URIs gain the UI links the catalog renders for Homarr
  (`apps/homarr/generated/apps.json`, entries of `apps/<app>/compose.yml`);
- for the services of UI_LOGINS, the admin username and the password already kept in a
  custom field are copied into the login, so the browser extension can fill the UI.

It only adds: an existing URI or password is never changed, and a username is replaced only
when it is the `homelab:<app>` placeholder of import_env_to_bitwarden.py. Prints names and
counts only. Dry run by default; --apply writes with BW_SESSION from the environment.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from import_env_to_bitwarden import edit_item, exact_items, sync_after_write
from render_from_bitwarden import BitwardenClient, SecretsError, load_manifest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config/secrets/manifest.json"
HOMARR = ROOT / "apps/homarr/generated/apps.json"

# app -> (username, or "field:<NAME>" to read it from the item; field holding the password).
UI_LOGINS = {
    "defectdojo": ("field:DD_ADMIN_USER", "DD_ADMIN_PASSWORD"),
    "dependency-track": ("admin", "DT_ADMIN_PASSWORD"),
    "grafana": ("admin", "GRAFANA_ADMIN_PASSWORD"),
    "keycloak": ("admin", "KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD"),
    "langflow": ("langflow", "LANGFLOW_SUPERUSER_PASSWORD"),
    "litellm": ("field:UI_USERNAME", "UI_PASSWORD"),
    "minio": ("minio", "MINIO_ROOT_PASSWORD"),
    "ntopng": ("admin", "NTOPNG_ADMIN_PASSWORD"),
}


def ui_urls(apps: list[dict[str, Any]], app: str) -> list[str]:
    source = f"apps/{app}/compose.yml"
    return sorted({entry["href"] for entry in apps if entry.get("sourcePath") == source and entry.get("href")})


def complete(item: dict[str, Any], app: str, urls: list[str]) -> tuple[dict[str, Any], list[str]]:
    """Return the item with what is missing added, and the names of the changes."""
    item = json.loads(json.dumps(item))
    login = item.setdefault("login", {}) or {}
    item["login"] = login
    changes: list[str] = []
    uris = list(login.get("uris") or [])
    known = {u.get("uri") for u in uris}
    added = [url for url in urls if url not in known]
    if added:
        login["uris"] = uris + [{"match": None, "uri": url} for url in added]
        changes.append(f"uri+{len(added)}")
    if app in UI_LOGINS:
        username, password_field = UI_LOGINS[app]
        fields = {f.get("name"): f.get("value") for f in item.get("fields") or []}
        if username.startswith("field:"):
            username = fields.get(username.removeprefix("field:")) or ""
        current = login.get("username") or ""
        if username and (not current or current == f"homelab:{app}") and current != username:
            login["username"] = username
            changes.append("username")
        if not login.get("password") and fields.get(password_field):
            login["password"] = fields[password_field]
            changes.append("password")
        elif not fields.get(password_field):
            changes.append(f"no {password_field} field")
    return item, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write Vaultwarden (default: dry run)")
    parser.add_argument("--app", action="append", dest="apps", help="limit to these manifest apps")
    args = parser.parse_args()
    manifest = load_manifest(MANIFEST)
    apps = json.loads(HOMARR.read_text(encoding="utf-8"))["applications"]
    folder = manifest["folder"]
    client = BitwardenClient(session=os.environ.get("BW_SESSION", ""), server=manifest["server"])
    client.verify()
    client.verify_folder(folder["id"], folder["name"])

    written: list[str] = []
    for spec in manifest["items"]:
        if args.apps and spec["app"] not in args.apps:
            continue
        matches = exact_items(client, name=spec["item"], folder_id=folder["id"])
        if len(matches) != 1:
            print(f"SKIP {spec['item']}: {len(matches)} items")
            continue
        if matches[0].get("type") != 1:
            print(f"SKIP {spec['item']}: not a login item")
            continue
        item, changes = complete(matches[0], spec["app"], ui_urls(apps, spec["app"]))
        writes = [c for c in changes if not c.startswith("no ")]
        print(f"{'UPDATE' if writes else 'OK'} {spec['item']}: {', '.join(changes) or 'nothing to add'}")
        if writes and args.apply:
            edit_item(client, item_id=matches[0]["id"], payload=item)
            written.append(spec["item"])
    if args.apply and written:
        sync_after_write(client, written)
    print(f"== {'applied' if args.apply else 'dry run'}: {len(written)} item(s) written")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SecretsError as exc:
        raise SystemExit(f"error: {exc}") from exc
