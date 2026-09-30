"""Reject duplicate definitions of shell runtime primitives with canonical owners."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

FUNCTION_RE = re.compile(
    r"^\s*(?:function\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"\s*(?:\(\s*\))?\s*\{\s*(?:#.*)?$"
)


@dataclass(frozen=True)
class Primitive:
    name: str
    owner: Path


def load_manifest(root: Path, manifest_path: Path) -> list[Primitive]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1:
        raise ValueError("runtime primitive manifest schemaVersion must be 1")

    raw_primitives = payload.get("primitives")
    if not isinstance(raw_primitives, list) or not raw_primitives:
        raise ValueError("runtime primitive manifest must contain a non-empty primitives list")

    primitives: list[Primitive] = []
    seen_names: set[str] = set()
    for index, raw in enumerate(raw_primitives):
        if not isinstance(raw, dict):
            raise ValueError(f"primitives[{index}] must be an object")
        name = raw.get("name")
        owner = raw.get("owner")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"primitives[{index}].name is invalid")
        if name in seen_names:
            raise ValueError(f"duplicate primitive in manifest: {name}")
        if not isinstance(owner, str) or not owner.startswith("scripts/") or not owner.endswith(".sh"):
            raise ValueError(f"primitives[{index}].owner must be a scripts/*.sh path")
        owner_path = Path(owner)
        if not (root / owner_path).is_file():
            raise ValueError(f"canonical owner does not exist: {owner}")
        seen_names.add(name)
        primitives.append(Primitive(name=name, owner=owner_path))

    return primitives


def scan_definitions(root: Path) -> dict[str, list[tuple[Path, int]]]:
    definitions: dict[str, list[tuple[Path, int]]] = {}
    scripts_root = root / "scripts"
    for path in sorted(scripts_root.rglob("*.sh")):
        relative = path.relative_to(root)
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = FUNCTION_RE.match(line)
            if match is None:
                continue
            definitions.setdefault(match.group("name"), []).append((relative, line_number))
    return definitions


def check(root: Path, manifest_path: Path) -> list[str]:
    primitives = load_manifest(root, manifest_path)
    definitions = scan_definitions(root)
    failures: list[str] = []

    for primitive in primitives:
        locations = definitions.get(primitive.name, [])
        owner_locations = [
            (path, line_number)
            for path, line_number in locations
            if path == primitive.owner
        ]
        foreign_locations = [
            (path, line_number)
            for path, line_number in locations
            if path != primitive.owner
        ]

        if len(owner_locations) != 1:
            rendered = ", ".join(f"{path}:{line}" for path, line in owner_locations) or "<none>"
            failures.append(
                "QG_RUNTIME_PRIMITIVE_OWNER: "
                f"{primitive.name} must be defined exactly once in {primitive.owner}; "
                f"found {rendered}"
            )

        if foreign_locations:
            rendered = ", ".join(f"{path}:{line}" for path, line in foreign_locations)
            failures.append(
                "QG_RUNTIME_PRIMITIVE_DUPLICATE: "
                f"{primitive.name} is owned by {primitive.owner} but also defined at {rendered}"
            )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate unique ownership of migrated shell runtime primitives."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("config/quality/runtime-primitives.json"),
    )
    args = parser.parse_args()

    root = args.root.resolve()
    manifest_path = args.manifest
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path

    try:
        failures = check(root, manifest_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"QG_RUNTIME_PRIMITIVE_CONFIG: {exc}", file=sys.stderr)
        return 2

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1

    print("OK: migrated runtime primitives have one canonical shell owner")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
