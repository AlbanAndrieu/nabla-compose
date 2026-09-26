#!/usr/bin/env python3
"""Generate standard catalog-v2 read models from Backstage descriptors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from nabla_ops.catalog_exports import build_standard_artifacts  # noqa: E402


def descriptor_paths() -> list[Path]:
    paths = [ROOT / "catalog" / "catalog-info.yaml"]
    paths.extend(sorted((ROOT / "apps").glob("*/catalog-info.yaml")))
    return [path for path in paths if path.is_file()]


def render(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "catalog" / "generated",
    )
    args = parser.parse_args()

    artifacts = build_standard_artifacts(descriptor_paths())
    stale: list[str] = []

    for name, payload in artifacts.items():
        path = args.output_dir / name
        expected = render(payload)
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                stale.append(str(path.relative_to(ROOT)))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected, encoding="utf-8")

    if stale:
        print("stale catalog-v2 artifacts:")
        for path in stale:
            print(f" - {path}")
        print("run: python scripts/generate-catalog-v2-artifacts.py")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
