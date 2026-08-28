#!/usr/bin/env python3
"""Import selected environment variables into a Vaultwarden folder."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_FOLDER_ID = "44a92b83-2762-4fa5-a238-f84396fd26f9"
ENVIRONMENT_VARIABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def run_bw(*arguments: str, input_text: str | None = None) -> str:
    try:
        result = subprocess.run(
            ["bw", *arguments],
            check=True,
            input=input_text,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        fail("missing command: bw")
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or "Bitwarden CLI command failed"
        fail(detail)
    return result.stdout


def read_manifest(path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        columns = line.split()
        if len(columns) > 2:
            fail(f"too many columns on manifest line {line_number}")
        environment_variable = columns[0]
        if not ENVIRONMENT_VARIABLE.fullmatch(environment_variable):
            fail(f"invalid environment variable name: {environment_variable}")
        item_name = columns[1] if len(columns) == 2 else environment_variable
        entries.append((environment_variable, item_name))
    return entries


def find_exact_item(folder_id: str, item_name: str) -> dict[str, object] | None:
    items = json.loads(
        run_bw("list", "items", "--folderid", folder_id, "--search", item_name)
    )
    matches = [
        item
        for item in items
        if item.get("folderId") == folder_id and item.get("name") == item_name
    ]
    if len(matches) > 1:
        fail(f"multiple exact items named {item_name} exist in the TrueNAS folder")
    return matches[0] if matches else None


def write_item(
    folder_id: str,
    environment_variable: str,
    item_name: str,
    secret_value: str,
    existing_item: dict[str, object] | None,
) -> str:
    if existing_item:
        item = json.loads(run_bw("get", "item", str(existing_item["id"])))
        action = "update"
    else:
        item = json.loads(run_bw("get", "template", "item"))
        item["notes"] = (
            "Imported from an environment variable; rotate after verification."
        )
        action = "create"

    item.update({"folderId": folder_id, "type": 1, "name": item_name})
    login = item.setdefault("login", {})
    if not isinstance(login, dict):
        fail(f"unexpected login data for item: {item_name}")
    login.update({"username": environment_variable, "password": secret_value})

    encoded_item = run_bw("encode", input_text=json.dumps(item))
    if action == "update":
        run_bw("edit", "item", str(item["id"]), input_text=encoded_item)
    else:
        run_bw("create", "item", input_text=encoded_item)
    return action


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import already-loaded environment variables into Vaultwarden."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    if not arguments.manifest.is_file():
        fail(f"manifest is not readable: {arguments.manifest}")
    if not os.environ.get("BW_SESSION"):
        fail("BW_SESSION must contain an unlocked bw session")
    folder_id = os.environ.get("BW_FOLDER_ID", DEFAULT_FOLDER_ID)

    run_bw("sync")
    for environment_variable, item_name in read_manifest(arguments.manifest):
        if environment_variable not in os.environ:
            fail(f"variable is not exported: {environment_variable}")
        secret_value = os.environ[environment_variable]
        if not secret_value:
            fail(f"variable is empty: {environment_variable}")

        existing_item = find_exact_item(folder_id, item_name)
        action = "update" if existing_item else "create"
        if not arguments.dry_run:
            action = write_item(
                folder_id,
                environment_variable,
                item_name,
                secret_value,
                existing_item,
            )
        print(f"{action} {item_name} from {environment_variable}")

    if not arguments.dry_run:
        run_bw("sync")


if __name__ == "__main__":
    try:
        main()
    except (json.JSONDecodeError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
