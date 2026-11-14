#!/usr/bin/env python3
"""Read-only tracked source hotspots, grouped by operational ownership.

Counts physical/nonblank lines, not complexity or executable statements.
No dependency install, network access, secrets, or working-tree mutation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS = frozenset({
    ".py", ".sh", ".bash", ".js", ".jsx", ".ts", ".tsx",
    ".mjs", ".cjs", ".go", ".rs", ".java", ".php", ".sql",
})
MAX_FILE_BYTES = 2 * 1024 * 1024


def topic(path: str) -> str:
    """One deterministic topic per tracked file; tests stay a separate cost."""
    if path.startswith("tests/"):
        return "tests"
    if path.startswith("scripts/truenas/"):
        return "truenas"
    if path.startswith("scripts/pfsense/"):
        return "pfsense"
    if path.startswith("scripts/talos/") or path.startswith("kubernetes/"):
        return "talos-kubernetes"
    if path.startswith("scripts/workstation/"):
        return "workstation-openclaw"
    if path.startswith("scripts/secrets/"):
        return "secrets"
    if path.startswith("scripts/quality/") or "agent-quality" in path:
        return "agent-quality"
    if path.startswith("scripts/nabla_ops/") or any(
        key in path for key in ("catalog", "topology", "service-consumer")
    ):
        return "catalog-topology"
    if path.startswith("scripts/"):
        return "operations-other"
    if path.startswith("nabla/api/assets/"):
        return "frontend-ui"
    if path.startswith(("nabla/api/", "nabla/integrations/")):
        return "fastapi-observability"
    if path.startswith("nabla/"):
        return "fastapi-core"
    if path.startswith(".agents/skills/"):
        return "agent-skills"
    return "other-source"


def tracked_paths(root: Path) -> list[str]:
    """Use Git's own index, not recursive directory crawling."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=False, timeout=15,
    )
    if result.returncode:
        raise RuntimeError("Git tracked-file inventory unavailable; no measurements made")
    return sorted(value.decode("utf-8", errors="surrogateescape")
                  for value in result.stdout.split(b"\0") if value)


def scan(root: Path, paths: Iterable[str], *, include_tests: bool = True) -> dict:
    """Count only checked-out, non-symlink tracked code; no runtime probes."""
    rows: list[dict] = []
    topics: dict[str, dict[str, int]] = {}
    root = root.resolve()
    skipped = 0
    for name in paths:
        if Path(name).suffix.lower() not in EXTENSIONS or (not include_tests and name.startswith("tests/")):
            continue
        candidate = root / name
        if (
            candidate.is_symlink()
            or not candidate.resolve(strict=False).is_relative_to(root)
            or not candidate.is_file()
        ):
            skipped += 1
            continue
        try:
            size = candidate.stat().st_size
            if size > MAX_FILE_BYTES:
                skipped += 1
                continue
            content = candidate.read_bytes()
        except OSError:
            skipped += 1
            continue
        if b"\0" in content:
            skipped += 1
            continue
        lines = content.splitlines()
        physical = len(lines)
        nonblank = sum(bool(line.strip()) for line in lines)
        label = topic(name)
        rows.append({"path": name, "topic": label, "lines": physical,
                     "nonblank_lines": nonblank, "bytes": len(content)})
        stat = topics.setdefault(label, {"files": 0, "lines": 0, "nonblank_lines": 0, "bytes": 0})
        stat["files"] += 1
        stat["lines"] += physical
        stat["nonblank_lines"] += nonblank
        stat["bytes"] += len(content)
    rows.sort(key=lambda item: (-item["lines"], item["path"]))
    return {
        "schema": "nabla-code-hotspots/v1", "source": "git-index-local",
        "scope": "tracked source files; physical lines include comments and blanks",
        "files": len(rows), "skipped": skipped,
        "total_lines": sum(row["lines"] for row in rows),
        "total_bytes": sum(row["bytes"] for row in rows),
        "topics": [{"topic": label, **stats} for label, stats in
                   sorted(topics.items(), key=lambda entry: (-entry[1]["lines"], entry[0]))],
        "files_ranked": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--min-lines", type=int, default=300)
    parser.add_argument("--exclude-tests", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 100 or not 0 <= args.min_lines <= 100000:
        parser.error("--limit must be 1..100 and --min-lines 0..100000")
    try:
        report = scan(args.root, tracked_paths(args.root), include_tests=not args.exclude_tests)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"NOT_RUN: {exc}", file=sys.stderr)
        return 2
    rows = [row for row in report.pop("files_ranked") if row["lines"] >= args.min_lines]
    report["largest_files"] = rows[:args.limit]
    report["large_file_count"] = len(rows)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(
            f"Tracked code: {report['files']} files / "
            f"{report['total_lines']} physical lines; skipped={report['skipped']}"
        )
        for entry in report["topics"]:
            print(f"  {entry['topic']}: {entry['lines']} lines ({entry['files']} files)")
        print("Largest files (physical lines):")
        for row in report["largest_files"]:
            print(f"  {row['lines']:>6}  {row['topic']:<24}  {row['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
