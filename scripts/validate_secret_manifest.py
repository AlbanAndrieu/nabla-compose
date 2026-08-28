#!/usr/bin/env python3
"""Validate the repository-owned secret reference manifest.

This validator never reads secret values. It only checks names, references, rotation
policy and duplicate environment-variable declarations so CI can enforce the contract
without access to Vaultwarden.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
ITEM_NAME = re.compile(r"^nabla/[a-z0-9][a-z0-9-]*(?:/[a-z0-9][a-z0-9-]*)+$")
ALLOWED_ROTATION = {
    "preserve",
    "preserve-until-cutover",
    "preserve-until-db-cutover",
    "rotatable",
}


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if payload.get("schemaVersion") != 1:
        raise ValueError("schemaVersion must be 1")
    if not isinstance(payload.get("services"), dict) or not payload["services"]:
        raise ValueError("services must be a non-empty object")
    return payload


def validate_manifest(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seen_env: dict[str, str] = {}

    for service, entries in sorted(payload["services"].items()):
        if not isinstance(service, str) or not service or service.lower() != service:
            errors.append(f"invalid service key: {service!r}")
            continue
        if not isinstance(entries, list) or not entries:
            errors.append(f"{service}: mappings must be a non-empty list")
            continue

        for index, entry in enumerate(entries):
            prefix = f"{service}[{index}]"
            if not isinstance(entry, dict):
                errors.append(f"{prefix}: mapping must be an object")
                continue

            env_name = entry.get("env")
            item_name = entry.get("item")
            field_name = entry.get("field")
            rotation = entry.get("rotation")
            required = entry.get("required")

            if not isinstance(env_name, str) or not ENV_NAME.fullmatch(env_name):
                errors.append(f"{prefix}: invalid env name {env_name!r}")
            elif env_name in seen_env:
                errors.append(
                    f"{prefix}: env {env_name} already declared by {seen_env[env_name]}"
                )
            else:
                seen_env[env_name] = service

            if not isinstance(item_name, str) or not ITEM_NAME.fullmatch(item_name):
                errors.append(f"{prefix}: invalid item reference {item_name!r}")
            if not isinstance(field_name, str) or not field_name.strip():
                errors.append(f"{prefix}: field must be a non-empty string")
            if rotation not in ALLOWED_ROTATION:
                errors.append(f"{prefix}: unsupported rotation policy {rotation!r}")
            if not isinstance(required, bool):
                errors.append(f"{prefix}: required must be boolean")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        default=Path("config/secrets/bitwarden-map.json"),
    )
    args = parser.parse_args()

    try:
        payload = load_manifest(args.manifest)
    except ValueError as exc:
        print(f"secret manifest error: {exc}", file=sys.stderr)
        return 1

    errors = validate_manifest(payload)
    if errors:
        for error in errors:
            print(f"secret manifest error: {error}", file=sys.stderr)
        return 1

    references = sum(len(entries) for entries in payload["services"].values())
    print(
        f"secret manifest valid: {len(payload['services'])} services, "
        f"{references} references"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
