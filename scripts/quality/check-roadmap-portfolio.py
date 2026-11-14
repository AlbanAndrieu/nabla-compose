#!/usr/bin/env python3
"""Validate and export the active Homelab portfolio without network or secrets.

Only the dedicated Markdown table is parsed. Historical narratives are not
promoted to active work. No GitHub, TrueNAS, Vaultwarden or shell access.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
RELATIVE = Path("docs/roadmap-portfolio.md")
HEADER = "## Backlog arbitrable"
FIELDS = ("id", "priority", "owner", "code", "runtime", "next_proof")
PRIORITIES = {"P0", "P1", "P2"}
CODE_STATES = {"CODED", "TESTED", "DEPLOYED", "PARTIAL", "PLANNED", "NOT_VERIFIED"}
RUNTIME_STATES = {"ACCEPTED", "NOT_VERIFIED", "PARTIAL"}
APPROVED_ORDER = ("H01", "H02", "H04", "H05", "H12", "H13", "H16")
ROW = re.compile(r"^H[0-9]{2}$")
LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")


def audit(root: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Return validated rows and bounded diagnostics; never mutate the source."""
    path = root / RELATIVE
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return [], [f"{RELATIVE}: missing or unreadable"]
    if HEADER not in source:
        return [], [f"{RELATIVE}: missing {HEADER}"]
    section = source.split(HEADER, 1)[1].split("\n## ", 1)[0]
    rows: list[dict[str, str]] = []
    issues: list[str] = []
    seen: set[str] = set()
    lines = section.splitlines()
    previous_row: int | None = None
    for index, line in enumerate(lines):
        if not line.startswith("| H"):
            continue
        # A blank line between active rows terminates a Markdown table,
        # hiding subsequent work items from rendered roadmaps.
        if previous_row is not None and any(
            not candidate.strip() for candidate in lines[previous_row + 1:index]
        ):
            issues.append("active Markdown table is split by a blank line")
        previous_row = index
        columns = [item.strip() for item in line.strip().strip("|").split("|")]
        if len(columns) != len(FIELDS):
            issues.append("table row has an invalid column count")
            continue
        item = dict(zip(FIELDS, columns, strict=True))
        identifier = item["id"]
        if not ROW.fullmatch(identifier) or identifier in seen:
            issues.append(f"{identifier}: invalid or duplicate ID")
        seen.add(identifier)
        if item["priority"] not in PRIORITIES:
            issues.append(f"{identifier}: invalid priority")
        if item["code"] not in CODE_STATES:
            issues.append(f"{identifier}: invalid code status")
        if item["runtime"] not in RUNTIME_STATES:
            issues.append(f"{identifier}: invalid runtime status")
        if not item["owner"] or not item["next_proof"]:
            issues.append(f"{identifier}: missing owner or next proof")
        for target in LINK.findall(item["next_proof"]):
            if "://" in target or target.startswith(("mailto:", "#")):
                continue
            target_path = (path.parent / target.split("#", 1)[0]).resolve()
            if not target_path.is_relative_to(root.resolve()) or not target_path.is_file():
                issues.append(f"{identifier}: missing/escaping local link: {target}")
        rows.append(item)
    if not rows:
        issues.append("no active portfolio rows")
    order = re.search(r"^## Séquence approuvée — (.+)$", source, re.M)
    if not order or "14 novembre 2026" not in order.group(1):
        issues.append("approved execution heading must reference 14 novembre 2026")
    sequence = source.split("## Séquence approuvée — ", 1)[-1].split("\n## ", 1)[0]
    actual_order = tuple(re.findall(r"^\\|\\s*([1-7])\\s*\\|\\s*\\*\\*(H[0-9]{2})", sequence, re.M))
    if tuple(identifier for _, identifier in actual_order) != APPROVED_ORDER or tuple(n for n, _ in actual_order) != tuple(map(str, range(1, len(APPROVED_ORDER) + 1))):
        issues.append("approved execution table must list H01 → H02 → H04 → H05 → H12 → H13 → H16")
    if rows and not {"P0", "P1", "P2"}.issubset({row["priority"] for row in rows}):
        issues.append("all three priority bands must be represented")
    return rows, issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="validate table (default)")
    mode.add_argument("--json", action="store_true", help="emit validated active rows")
    mode.add_argument("--worklist", action="store_true", help="emit approved work in execution order")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    entries, errors = audit(args.root)
    if errors:
        for error in errors:
            print(f"FAIL {error}", file=sys.stderr)
        return 1
    if args.json or args.worklist:
        if args.worklist:
            by_id = {entry["id"]: entry for entry in entries}
            if any(identifier not in by_id for identifier in APPROVED_ORDER):
                print("FAIL approved item missing", file=sys.stderr)
                return 1
            entries = [by_id[identifier] for identifier in APPROVED_ORDER]
        print(json.dumps(entries, ensure_ascii=False, indent=2))
    else:
        print(f"PASS roadmap portfolio: {len(entries)} active items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
