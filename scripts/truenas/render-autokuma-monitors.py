#!/usr/bin/env python3
"""Render generated Gatus-derived monitors as AutoKuma native per-ID JSON files."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile

IDENTIFIER = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def native_definitions(source: Path) -> dict[str, str]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("AutoKuma generated manifest must be a non-empty array")
    result: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("AutoKuma monitor must be an object")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
            raise ValueError("Invalid AutoKuma monitor ID")
        if identifier in result:
            raise ValueError(f"Duplicate AutoKuma monitor ID: {identifier}")
        native = {key: value for key, value in item.items() if key != "id"}
        if native.get("type") not in {"http", "port", "ping"}:
            raise ValueError(f"Unsupported AutoKuma monitor type: {identifier}")
        if not isinstance(native.get("name"), str) or not native["name"]:
            raise ValueError(f"Missing AutoKuma name: {identifier}")
        result[identifier] = json.dumps(native, indent=2, ensure_ascii=False) + "\n"
    return result


def apply(definitions: dict[str, str], directory: Path) -> None:
    if directory.exists() and directory.is_symlink():
        raise ValueError("AutoKuma output directory must not be a symlink")
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise ValueError("AutoKuma destination is not a directory")
    expected = {f"nabla-{name}.json" for name in definitions}
    # Refuse to overwrite foreign files, symlinks or unexpected paths.
    for file in directory.iterdir():
        if file.is_symlink():
            raise ValueError("AutoKuma target directory contains a symlink")
        if file.name.endswith(".json") and not file.name.startswith("nabla-"):
            raise ValueError("AutoKuma target directory contains unmanaged JSON")
    for identifier, content in definitions.items():
        target = directory / f"nabla-{identifier}.json"
        if target.exists() and not target.is_file():
            raise ValueError("AutoKuma target is not a regular file")
        fd, staged = tempfile.mkstemp(prefix=".nabla-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(staged, 0o644)
            os.replace(staged, target)
        finally:
            if os.path.exists(staged):
                os.unlink(staged)
    for stale in directory.glob("nabla-*.json"):
        if stale.name not in expected:
            stale.unlink()
    print(f"AutoKuma native monitors materialized: {len(definitions)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("apps/autokuma/static/generated-monitors.json"))
    parser.add_argument("--output-dir", type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--validate-only", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply and args.output_dir is None:
        parser.error("--apply requires --output-dir")
    try:
        definitions = native_definitions(args.source)
        if args.apply:
            apply(definitions, args.output_dir)
        else:
            print(f"AutoKuma native manifest valid: {len(definitions)}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(1, f"AutoKuma materialization rejected: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
