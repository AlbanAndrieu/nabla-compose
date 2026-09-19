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
import sys
from pathlib import Path
from typing import Any

from render_from_bitwarden import BitwardenClient, SecretsError, load_manifest


def source_env_name(spec: dict[str, Any]) -> str:
    value = spec.get("importEnv", spec.get("env"))
    if not isinstance(value, str) or not value:
        raise SecretsError(f"{spec.get('env', '<unknown>')}: invalid importEnv")
    return value


def decode_dotenv_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] == "'":
        body = value[1:-1]
        return body.replace("\\'", "'").replace("\\\\", "\\")
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse a narrow dotenv subset without executing shell syntax."""

    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise SecretsError("dotenv input contains a non-assignment line")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum() or not key[0].isalpha():
            raise SecretsError(f"invalid dotenv variable name: {key!r}")
        value = decode_dotenv_value(raw_value)
        if "\x00" in value or "\n" in value or "\r" in value:
            raise SecretsError(f"{key}: multiline/NUL dotenv values are unsupported")
        values[key] = value
    return values


def collect_values(
    app_spec: dict[str, Any],
    *,
    source_values: dict[str, str] | None = None,
) -> tuple[dict[str, str], set[str]]:
    """Collect values without sourcing shell code or printing secret material."""

    source_values = source_values if source_values is not None else dict(os.environ)
    values: dict[str, str] = {}
    supplied: set[str] = set()
    missing_count = 0

    for spec in app_spec["secrets"]:
        import_name = source_env_name(spec)
        target_name = spec["env"]
        allow_empty = spec.get("allowEmpty", False)

        if import_name in source_values:
            value = source_values[import_name]
            supplied.add(import_name)
        elif target_name in source_values:
            # Historical .env.secrets files normally contain the target runtime
            # name rather than the migration-friendly importEnv alias.
            value = source_values[target_name]
            supplied.add(target_name)
        elif allow_empty:
            value = ""
        else:
            missing_count += 1
            continue

        if not value and not allow_empty:
            missing_count += 1
            continue
        if "\x00" in value or "\n" in value or "\r" in value:
            raise SecretsError(
                f"{app_spec['app']}: a supplied secret contains unsupported multiline/NUL data"
            )
        values[target_name] = value

    if missing_count:
        raise SecretsError(
            f"{app_spec['app']}: {missing_count} required source value(s) are missing"
        )
    return values, supplied


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
    supplied_sources: set[str] | None = None,
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

    supplied_sources = supplied_sources or set()
    for spec in app_spec["secrets"]:
        target_env = spec["env"]
        source_names = {source_env_name(spec), target_env}
        if (
            existing is not None
            and spec.get("allowEmpty", False)
            and not (source_names & supplied_sources)
        ):
            # Partial updates must not erase an existing optional provider key just
            # because its source variable was not exported in this shell.
            continue

        value = values[target_env]
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


def sync_after_write(client: BitwardenClient, written_items: list[str]) -> bool:
    """Refresh the local CLI cache without misreporting completed remote writes.

    Vaultwarden can accept a create/edit request and then become temporarily unavailable
    before the final ``bw sync``. Treat that as a post-write cache refresh warning rather
    than claiming the write itself failed. Operators must verify the exact item before
    attempting another ``--apply`` so a stale CLI cache cannot cause a duplicate create.
    """

    try:
        client._run("sync", with_session=True)
    except SecretsError as exc:
        item_summary = ", ".join(written_items) or "Vaultwarden item(s)"
        print(
            "WARNING: Vaultwarden write completed for "
            f"{item_summary}, but the post-write bw sync failed: {exc}. "
            "Do not rerun --apply blindly; retry `bw sync` and verify the exact item first.",
            file=sys.stderr,
        )
        return False
    return True


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
        help="allow replacing explicitly supplied mapped values in an existing exact item",
    )
    parser.add_argument(
        "--dotenv-file",
        help=(
            "read source values from a dotenv file instead of the process environment; "
            "use '-' for stdin. The file is parsed as data and is never sourced."
        ),
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

    source_values: dict[str, str] | None = None
    if args.dotenv_file:
        if args.dotenv_file == "-":
            source_values = parse_dotenv(sys.stdin.read())
        else:
            source_values = parse_dotenv(
                Path(args.dotenv_file).read_text(encoding="utf-8")
            )

    collected: dict[str, tuple[dict[str, str], set[str]]] = {
        item["app"]: collect_values(item, source_values=source_values)
        for item in selected
    }

    if not args.apply:
        for item in selected:
            _, supplied = collected[item["app"]]
            mapping_count = len(item["secrets"])
            print(
                f"dry-run: {item['app']} -> {item['item']} "
                f"({len(supplied)}/{mapping_count} mapped source value(s) explicitly supplied; names and values suppressed)"
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

    written_items: list[str] = []
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
        values, supplied = collected[app_spec["app"]]
        payload = make_item(
            app_spec=app_spec,
            folder_id=folder["id"],
            values=values,
            existing=existing,
            supplied_sources=supplied,
        )

        if existing is None:
            create_item(client, payload)
            written_items.append(app_spec["item"])
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
        written_items.append(app_spec["item"])
        print(f"updated Vaultwarden item: {app_spec['item']}")

    sync_after_write(client, written_items)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SecretsError as exc:
        raise SystemExit(f"error: {exc}") from exc
