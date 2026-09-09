#!/usr/bin/env python3
"""List homelab services that still rely on the default production environment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog" / "homelab-services.json"
ALLOWED = {"production", "staging", "dev"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    services = payload.get("services", [])
    implicit: list[dict[str, str]] = []
    invalid: list[dict[str, str]] = []

    for service in services:
        if not isinstance(service, dict):
            continue
        name = str(service.get("name") or "").strip()
        environment = service.get("environment")
        if environment is None:
            implicit.append({"name": name, "effectiveEnvironment": "production"})
        elif environment not in ALLOWED:
            invalid.append({"name": name, "environment": str(environment)})

    if args.json:
        print(json.dumps({"implicitProduction": implicit, "invalid": invalid}, indent=2))
    else:
        print(f"implicit production: {len(implicit)}")
        for row in implicit:
            print(f"- {row['name']}")
        if invalid:
            print(f"invalid environments: {len(invalid)}")
            for row in invalid:
                print(f"- {row['name']}: {row['environment']}")

    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())
