#!/usr/bin/env python3
"""Import already-exported environment variables into the TrueNAS Vaultwarden folder.

The script intentionally reads the current process environment instead of parsing or sourcing
shell files. Existing git-crypt files can therefore remain the trusted legacy source during
migration: source them yourself, review the dry-run, then use --apply.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from render_from_bitwarden import BitwardenClient, SecretsError, load_manifest


def source_env_name(spec: dict[str, Any]) -> str:
    value = spec.get("importEnv", spec.get("env"))
    if not isinstance(value, str) or not value:
        raise SecretsError(f"{spec.get('env', '<unknown>')}: invalid importEnv")
    return value


def collect_values(app_spec: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    missing: list[str] = []
    for spec in app_spec["secrets"]:
        env_name = source_env_name(spec)
        value = os.environ.get(env_name)
        if value is None or (not value and not spec.get("allowEmpty", False)):
            missing.append(env_name)
            continue
        if "\x00" in value or "\n" in value or "\r" in value:
            raise SecretsError(
                f"{app_spec['app']}/{env_name}: multiline/NUL values are unsupported"
            )
        values[spec["env"]] = value
    if missing:
        raise SecretsError(
            f"{app_spec['app']}: missing exported environment variable(s): "
            + ", ".join(sorted(missing))
        )
    return values


def exact_items(
    client: BitwardenClient,
    *,
    name: str,
    folder_id: str,
) -> list[dict[str, Any]]:
    raw = client._run(
        "list",
        "items",
        "--search",
        name,
        "--folderid",
        folder_id,
        with_session=True,
    )
    return [
        item
        for item in json.loads(raw)
        if isinstance(item, dict)
        and item.get("name") == name
        and item.get("folderId") == folder_id
    ]


def make_item(
    *,
    app_spec: dict[str, Any],
    folder_id: str,
    values: dict[str, str],
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = dict(existing or {})
    item["type"] = 1
    item["name"] = app_spec["item"]
    item["folderId"] = folder_id

    login = dict(item.get("login") or {})
    if not login.get("username"):
        login["username"] = f"homelab:{app_spec['app']}"
    item["login"] = login

    fields = [
        dict(field)
        for field in item.get("fields") or []
        if isinstance(field, dict)
    ]
    by_name = {
        field.get("name"): field
        for field in fields
        if isinstance(field.get("name"), str)
    }

    for spec in app_spec["secrets"]:
        value = values[spec["env"]]
        source = spec.get("source", "field")
        if source == "login.password":
            item["login"]["password"] = value
        elif source == "login.username":
            item["login"]["username"] = value
        else:
            field_name = spec["field"]
            field = by_name.get(field_name)
            if field is None:
                field = {"name": field_name, "type": 1}
                fields.append(field)
                by_name[field_name] = field
            field["value"] = value
            field["type"] = 1

    item["fields"] = fields
    return item


def encode_payload(client: BitwardenClient, payload: dict[str, Any]) -> str:
    return client._run(
        "encode",
        input_text=json.dumps(payload, separators=(",", ":")),
    )


def create_item(client: BitwardenClient, payload: dict[str, Any]) -> None:
    encoded = encode_payload(client, payload)
    # Bitwarden CLI accepts the encoded JSON on stdin. Secret material therefore does
    # not need to be put in the process argument vector.
    client._run("create", "item", with_session=True, input_text=encoded)


def edit_item(
    client: BitwardenClient,
    *,
    item_id: str,
    payload: dict[str, Any],
) -> None:
    encoded = encode_payload(client, payload)
    client._run(
        "edit",
        "item",
        item_id,
        with_session=True,
        input_text=encoded,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("config/secrets/manifest.json"),
    )
    parser.add_argument(
        "--app",
        action="append",
        dest="apps",
        help="import one app; repeat for multiple apps (default: all)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write to Vaultwarden; default is a metadata-only dry-run",
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="allow replacing mapped values in an existing exact item",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_manifest(args.manifest)

    requested = set(args.apps or [item["app"] for item in manifest["items"]])
    known = {item["app"] for item in manifest["items"]}
    unknown = sorted(requested - known)
    if unknown:
        raise SecretsError(f"unknown app(s): {', '.join(unknown)}")

    selected = [item for item in manifest["items"] if item["app"] in requested]
    collected = {item["app"]: collect_values(item) for item in selected}

    if not args.apply:
        for item in selected:
            names = ", ".join(source_env_name(spec) for spec in item["secrets"])
            print(
                f"dry-run: {item['app']} -> {item['item']} "
                f"(source env: {names}; no values printed)"
            )
        print("dry-run complete; rerun with --apply to write Vaultwarden")
        return 0

    folder = manifest["folder"]
    client = BitwardenClient(
        session=os.environ.get("BW_SESSION", ""),
        server=manifest["server"],
    )
    client.verify()
    client.verify_folder(folder["id"], folder["name"])

    for app_spec in selected:
        matches = exact_items(
            client,
            name=app_spec["item"],
            folder_id=folder["id"],
        )
        if len(matches) > 1:
            raise SecretsError(
                f"{app_spec['app']}: duplicate exact Vaultwarden items in TrueNAS folder"
            )
        existing = matches[0] if matches else None
        payload = make_item(
            app_spec=app_spec,
            folder_id=folder["id"],
            values=collected[app_spec["app"]],
            existing=existing,
        )

        if existing is None:
            create_item(client, payload)
            print(f"created Vaultwarden item: {app_spec['item']}")
            continue

        if not args.update_existing:
            raise SecretsError(
                f"{app_spec['app']}: item already exists; "
                "use --update-existing after reviewing the mapping"
            )
        item_id = existing.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise SecretsError(f"{app_spec['app']}: existing item has no id")
        edit_item(client, item_id=item_id, payload=payload)
        print(f"updated Vaultwarden item: {app_spec['item']}")

    client._run("sync", with_session=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SecretsError as exc:
        raise SystemExit(f"error: {exc}") from exc
