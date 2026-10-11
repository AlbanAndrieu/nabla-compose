#!/usr/bin/env python3
"""Read-only, bounded Docker resource ranking for TrueNAS operators.

No Docker environment, logs, inspect payloads, commands, or secrets are printed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys


def parse_size(text: str) -> int | None:
    units = {"B": 1, "kB": 1000, "MB": 1000**2, "GB": 1000**3,
             "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}
    import re

    m = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)\s*", text)
    return int(float(m.group(1)) * units[m.group(2)]) if m and m.group(2) in units else None


def collect(timeout: int) -> list[dict[str, object]]:
    proc = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
        capture_output=True, text=True, timeout=timeout, check=False,
    )
    if proc.returncode:
        raise RuntimeError("docker stats failed (stderr redacted)")
    rows = []
    for line in proc.stdout.splitlines():
        try:
            row = json.loads(line)
            name = str(row.get("Name", ""))[:100]
            cpu = float(str(row.get("CPUPerc", "0")).rstrip("%"))
            mem_pct = float(str(row.get("MemPerc", "0")).rstrip("%"))
            mem_bytes = parse_size(str(row.get("MemUsage", "")).split("/")[0])
            if not name or mem_bytes is None:
                continue
            rows.append({"name": name, "cpu_pct": cpu, "memory_bytes": mem_bytes,
                         "memory_limit_pct": mem_pct})
        except (ValueError, TypeError, KeyError):
            continue
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--cpu-warning", type=float, default=80)
    parser.add_argument("--memory-warning", type=float, default=85)
    args = parser.parse_args()
    if not 1 <= args.top <= 50 or not 1 <= args.timeout <= 60:
        parser.error("top must be 1..50; timeout must be 1..60")
    try:
        rows = collect(args.timeout)
    except (OSError, subprocess.TimeoutExpired, RuntimeError):
        print("WARN resource evidence unavailable; Docker or stats timed out")
        return 2
    if not rows:
        print("WARN no parsable Docker resource samples")
        return 2
    print(f"RESOURCE_SNAPSHOT containers={len(rows)} sample=one-shot (not trend or peak)")
    for metric, title in (("cpu_pct", "CPU"), ("memory_bytes", "MEMORY")):
        print(f"TOP_{title}")
        for row in sorted(rows, key=lambda x: x[metric], reverse=True)[:args.top]:
            print(f"  {row['name']} cpu_pct={row['cpu_pct']:.1f} "
                  f"mem_mib={row['memory_bytes'] / 1048576:.1f} "
                  f"mem_limit_pct={row['memory_limit_pct']:.1f}")
    hot = [r for r in rows if r["cpu_pct"] >= args.cpu_warning
           or r["memory_limit_pct"] >= args.memory_warning]
    print(f"RESOURCE_PRESSURE candidates={len(hot)} "
          "(thresholds are triage hints, not service-down evidence)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
