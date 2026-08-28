#!/usr/bin/env python3
"""Render a root-restricted Compose env file from Vaultwarden."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_FOLDER_ID = "44a92b83-2762-4fa5-a238-f84396fd26f9"
ENVIRONMENT_VARIABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def run_command(*arguments: str) -> str:
    try:
        result = subprocess.run(
            list(arguments),
            check=True,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        fail(f"missing command: {arguments[0]}")
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or f"{arguments[0]} command failed"
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


def find_exact_item(folder_id: str, item_name: str) -> dict[str, object]:
    items = json.loads(
        run_command(
            "bw", "list", "items", "--folderid", folder_id, "--search", item_name
        )
    )
    matches = [
        item
        for item in items
        if item.get("folderId") == folder_id and item.get("name") == item_name
    ]
    if len(matches) != 1:
        fail(f"expected one exact item named {item_name}; found {len(matches)}")
    return matches[0]


def dotenv_line(environment_variable: str, secret_value: str, item_name: str) -> str:
    if "\n" in secret_value or "\r" in secret_value:
        fail(f"multiline value requires a Docker secret file: {item_name}")
    escaped_value = secret_value.replace("'", "\\'")
    return f"{environment_variable}='{escaped_value}'\n"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a Compose .env file from the TrueNAS Vaultwarden folder."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    if not arguments.manifest.is_file():
        fail(f"manifest is not readable: {arguments.manifest}")
    if not os.environ.get("BW_SESSION"):
        fail("BW_SESSION must contain an unlocked bw session")
    folder_id = os.environ.get("BW_FOLDER_ID", DEFAULT_FOLDER_ID)

    repository_root = Path(
        run_command("git", "rev-parse", "--show-toplevel").strip()
    ).resolve()
    output = arguments.output.expanduser().resolve()
    if output == repository_root or repository_root in output.parents:
        fail("refusing to write a cleartext secret file inside the Git checkout")
    if not output.parent.is_dir():
        fail(f"output directory does not exist: {output.parent}")
    if output.exists() and not arguments.force:
        fail("output already exists; pass --force to replace it")

    run_command("bw", "sync")
    rendered_lines: list[str] = []
    for environment_variable, item_name in read_manifest(arguments.manifest):
        item = find_exact_item(folder_id, item_name)
        full_item = json.loads(run_command("bw", "get", "item", str(item["id"])))
        login = full_item.get("login")
        secret_value = login.get("password") if isinstance(login, dict) else None
        if not isinstance(secret_value, str) or not secret_value:
            fail(f"item has no login password: {item_name}")
        rendered_lines.append(
            dotenv_line(environment_variable, secret_value, item_name)
        )

    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".vaultwarden-env.", dir=output.parent
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.writelines(rendered_lines)
        temporary_path.chmod(0o600)
        temporary_path.replace(output)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    print(f"Rendered {output} with mode 0600")


if __name__ == "__main__":
    try:
        main()
    except (json.JSONDecodeError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
