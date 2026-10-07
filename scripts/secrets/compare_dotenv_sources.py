#!/usr/bin/env python3
"""Compare two bounded dotenv migration sources without printing secret values."""

from __future__ import annotations

import argparse
from pathlib import Path

import import_dotenv_to_bitwarden as legacy
from render_from_bitwarden import SecretsError, load_manifest


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "config" / "secrets" / "manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    return parser.parse_args()


def app_key_aliases(
    app: str,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, str]:
    manifest = load_manifest(manifest_path)
    matches = [item for item in manifest["items"] if item["app"] == app]
    if not matches:
        return {}
    if len(matches) != 1:
        raise SecretsError(f"{app}: expected exactly one manifest item")

    aliases: dict[str, str] = {}
    for secret in matches[0]["secrets"]:
        target = secret["env"]
        source = secret.get("importEnv", target)
        if source != target:
            aliases[source] = target
    return aliases


def normalize_keys(
    values: dict[str, str],
    aliases: dict[str, str],
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in values.items():
        target = aliases.get(key, key)
        if target in normalized and normalized[target] != value:
            raise SecretsError(
                f"dotenv aliases disagree for normalized key {target}"
            )
        normalized[target] = value
    return normalized


def compare_values(
    left: dict[str, str],
    right: dict[str, str],
) -> dict[str, list[str]]:
    left_keys = set(left)
    right_keys = set(right)
    shared = left_keys & right_keys
    return {
        "onlyLeft": sorted(left_keys - right_keys),
        "onlyRight": sorted(right_keys - left_keys),
        "sameValue": sorted(key for key in shared if left[key] == right[key]),
        "differentValue": sorted(key for key in shared if left[key] != right[key]),
    }


def main() -> int:
    args = parse_args()
    if not legacy.approved_app_env_path(args.app, args.left):
        raise SecretsError(f"left path is outside approved app dotenv roots: {args.left}")
    if not legacy.approved_app_env_path(args.app, args.right):
        raise SecretsError(f"right path is outside approved app dotenv roots: {args.right}")

    aliases = app_key_aliases(args.app)
    left = normalize_keys(
        legacy.parse_dotenv(legacy.read_root_bounded(args.left)),
        aliases,
    )
    right = normalize_keys(
        legacy.parse_dotenv(legacy.read_root_bounded(args.right)),
        aliases,
    )
    result = compare_values(left, right)

    print(f"app={args.app}")
    print(f"aliases={len(aliases)}")
    print(f"left={args.left} normalized_keys={len(left)}")
    print(f"right={args.right} normalized_keys={len(right)}")
    for label in ("onlyLeft", "onlyRight", "differentValue", "sameValue"):
        values = result[label]
        print(f"{label}={len(values)}")
        for key in values:
            print(f"  {key}")
    differs = (
        result["onlyLeft"]
        or result["onlyRight"]
        or result["differentValue"]
    )
    return 1 if differs else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SecretsError as exc:
        raise SystemExit(f"error: {exc}") from exc
