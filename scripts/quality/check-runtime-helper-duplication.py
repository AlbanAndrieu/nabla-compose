#!/usr/bin/env python3
"""Reject duplicate definitions of runtime helpers that already have canonical owners."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import re
import sys


CANONICAL_HELPERS = {
    "docker_orphan_shim_recovery_guard": Path("scripts/lib/docker.sh"),
    "truenas_lifecycle_mark": Path("scripts/lib/truenas.sh"),
    "truenas_lifecycle_errors_since": Path("scripts/lib/truenas.sh"),
    "truenas_app_state": Path("scripts/lib/truenas.sh"),
    "truenas_reconcile_custom_app": Path("scripts/lib/truenas.sh"),
    "truenas_wait_app_running": Path("scripts/lib/truenas.sh"),
    "truenas_dataset_query_by_id": Path("scripts/lib/truenas.sh"),
    "truenas_nfs_share_count_for_path": Path("scripts/lib/truenas.sh"),
    "secrets_assert_file": Path("scripts/lib/secrets.sh"),
    "secrets_get_value": Path("scripts/lib/secrets.sh"),
}

FUNCTION_RE = re.compile(
    r"^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s*\(\s*\))?\s*\{",
    re.MULTILINE,
)


def discover_definitions(root: Path) -> dict[str, list[Path]]:
    definitions: dict[str, list[Path]] = defaultdict(list)
    scripts_root = root / "scripts"
    if not scripts_root.is_dir():
        raise ValueError(f"scripts directory is missing: {scripts_root}")

    for path in sorted(scripts_root.rglob("*.sh")):
        relative = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        for match in FUNCTION_RE.finditer(text):
            helper = match.group(1)
            if helper in CANONICAL_HELPERS:
                definitions[helper].append(relative)
    return definitions


def validate(root: Path) -> list[str]:
    definitions = discover_definitions(root)
    failures: list[str] = []

    for helper, owner in CANONICAL_HELPERS.items():
        observed = definitions.get(helper, [])
        if observed == [owner]:
            continue
        rendered = ", ".join(path.as_posix() for path in observed) or "<missing>"
        failures.append(
            f"{helper}: expected only {owner.as_posix()}, found {rendered}"
        )
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reject duplicate or relocated definitions of runtime helpers that "
            "already have canonical scripts/lib owners."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root (defaults to the current checkout)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    try:
        failures = validate(root)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: runtime helper duplication check failed: {exc}", file=sys.stderr)
        return 2

    if failures:
        print("ERROR: duplicated or misplaced migrated runtime helpers:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print(
            "Source the canonical scripts/lib helper instead of copying its implementation.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: {len(CANONICAL_HELPERS)} migrated runtime helpers have one canonical owner"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
