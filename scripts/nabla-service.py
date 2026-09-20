#!/usr/bin/env python3
"""Read-only host-local Nabla service control CLI.

This CLI intentionally has no server, no Vaultwarden session handling and no
privileged mutation path. It is the reusable local core that FastAPI Sample can
later call through a bounded adapter.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from nabla_ops import InitializationStage, declared_apps, load_catalog  # noqa: E402

CATALOG = ROOT / "catalog" / "services.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    catalog = sub.add_parser("catalog", help="show normalized application intent")
    catalog.add_argument("--json", action="store_true")
    catalog.add_argument("--include-non-active", action="store_true")

    stages = sub.add_parser("stages", help="show initialization state machine")
    stages.add_argument("--json", action="store_true")
    return parser.parse_args()


def command_catalog(args: argparse.Namespace) -> int:
    rows = declared_apps(load_catalog(CATALOG), root=ROOT)
    if not args.include_non_active:
        rows = [row for row in rows if row["initializationEligible"]]
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0

    print(f"{'APP':24} {'STATUS':10} {'INIT':8} {'RUNTIME'}")
    for row in rows:
        print(
            f"{row['app'][:24]:24} {str(row['status'] or '-')[:10]:10} "
            f"{('yes' if row['initializationEligible'] else 'no'):8} "
            f"{row['runtimeId'] or '-'}"
        )
    return 0


def command_stages(args: argparse.Namespace) -> int:
    stages = [stage.value for stage in InitializationStage]
    if args.json:
        print(json.dumps({"stages": stages}, indent=2))
    else:
        print(" -> ".join(stages))
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "catalog":
        return command_catalog(args)
    if args.command == "stages":
        return command_stages(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
