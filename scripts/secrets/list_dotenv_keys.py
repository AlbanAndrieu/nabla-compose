#!/usr/bin/env python3
"""List dotenv key names from one approved legacy secret source, never values."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import audit_consumers
import import_dotenv_to_bitwarden as legacy
from render_from_bitwarden import SecretsError, load_manifest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config" / "secrets" / "manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True)
    parser.add_argument("--input", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if os.geteuid() == 0:
        raise SecretsError(
            "run as the operator; sudo is used only for the approved root-owned file read"
        )

    manifest = load_manifest(MANIFEST)
    source = legacy.choose_input(manifest, args.app, args.input)
    parsed = legacy.parse_dotenv(legacy.read_root_bounded(source))
    print(f"app={args.app} source={source} keys={len(parsed)}")
    for key in sorted(parsed):
        print(key)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SecretsError as exc:
        raise SystemExit(f"error: {exc}") from exc
