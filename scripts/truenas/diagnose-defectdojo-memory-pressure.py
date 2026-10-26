#!/usr/bin/env python3
"""Read-only TrueNAS memory pressure and DefectDojo attribution report.

Linux MemAvailable, memory PSI, cgroup OOM events, ZFS ARC and a bounded
Docker stats snapshot are independent signals. The tool never changes
ARC limits, cgroups, container state, or environment variables.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import subprocess
import sys

DEFECTDOJO_CONTAINERS = frozenset({
    "defectdojo", "defectdojo-uwsgi", "defectdojo-celeryworker",
    "defectdojo-celerybeat", "defectdojo-initializer",
})
MAX_DOCKER_OUTPUT = 256 * 1024


def read_memory_info(path: Path = Path("/proc/meminfo")) -> dict[str, int]:
    allowed = {"MemTotal", "MemAvailable", "MemFree", "SwapTotal",
               "SwapFree", "Cached", "SReclaimable", "Shmem"}
    values: dict[str, int] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([A-Za-z_()]+):\s+(\d+)\s+kB", line)
        if match and match.group(1) in allowed:
            values[match.group(1)] = int(match.group(2)) * 1024
    if not all(k in values for k in ("MemTotal", "MemAvailable",
                                    "SwapTotal", "SwapFree")):
        raise ValueError("memory_fields_unavailable")
    return values


def read_pressure(path: Path = Path("/proc/pressure/memory")) -> dict[str, float]:
    result: dict[str, float] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        fields = line.split()
        if not fields or fields[0] not in ("some", "full"):
            continue
        for field in fields[1:]:
            if field.startswith("avg10="):
                value = float(field.partition("=")[2])
                if math.isfinite(value) and value >= 0:
                    result[fields[0] + "_avg10_pct"] = value
    return result


def read_arc(path: Path = Path("/proc/spl/kstat/zfs/arcstats")) -> dict[str, int | str]:
    if not path.is_file():
        return {"state": "UNAVAILABLE"}
    values: dict[str, int] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0] in ("size", "c", "c_min"):
            try:
                values[fields[0]] = int(fields[2])
            except ValueError:
                pass
    if not all(k in values for k in ("size", "c_min")):
        return {"state": "UNVERIFIED"}
    size = max(0, values["size"])
    minimum = max(0, values["c_min"])
    return {
        "state": "OBSERVED",
        "size_bytes": size,
        "minimum_bytes": minimum,
        # ARC shrinkability is an estimate, not permission to reclaim memory.
        "potential_shrink_bytes": max(0, size - minimum),
    }


def read_memory_events(path: Path = Path("/sys/fs/cgroup/memory.events")) -> dict[str, int | str]:
    if not path.is_file():
        return {"state": "UNAVAILABLE"}
    result: dict[str, int | str] = {"state": "OBSERVED"}
    allowed = {"oom", "oom_kill", "oom_group_kill", "high", "max"}
    for line in path.read_text(encoding="ascii").splitlines():
        pair = line.split()
        if len(pair) == 2 and pair[0] in allowed and pair[1].isdigit():
            result[pair[0]] = int(pair[1])
    return result


def parse_size(text: str) -> int | None:
    units = {"B": 1, "kB": 1000, "MB": 1000**2, "GB": 1000**3,
             "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([A-Za-z]+)", text.strip())
    if match is None or match.group(2) not in units:
        return None
    return int(float(match.group(1)) * units[match.group(2)])


def docker_snapshot(timeout: int = 15) -> dict[str, object]:
    try:
        process = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "UNVERIFIED", "error_class": "DockerUnavailable"}
    if process.returncode or len(process.stdout) > MAX_DOCKER_OUTPUT:
        return {"status": "UNVERIFIED", "error_class": "DockerStatsUnavailable"}
    total_bytes = 0
    apps: list[dict[str, object]] = []
    top: list[dict[str, object]] = []
    for line in process.stdout.splitlines():
        try:
            obj = json.loads(line)
            name = obj.get("Name", "")
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", name):
                continue
            used = parse_size(str(obj.get("MemUsage", "")).split("/", 1)[0])
            if used is None:
                continue
            row = {"container": name, "memory_bytes": used}
            top.append(row)
            if name in DEFECTDOJO_CONTAINERS:
                total_bytes += used
                apps.append(row)
        except (ValueError, TypeError):
            continue
    return {
        "status": "OBSERVED" if top else "UNVERIFIED",
        "defectdojo_total_bytes": total_bytes,
        "defectdojo_containers": sorted(apps, key=lambda x: x["container"]),
        "top_memory_containers": sorted(
            top, key=lambda x: x["memory_bytes"], reverse=True
        )[:12],
        # Docker stats memory is a sample and may differ from process RSS.
        "note": "one-shot working set estimates; no causal attribution or peak memory",
    }


def assess(mem: dict[str, int], psi: dict[str, float],
           events: dict[str, int | str]) -> str:
    available_pct = 100 * mem["MemAvailable"] / max(1, mem["MemTotal"])
    full = psi.get("full_avg10_pct")
    some = psi.get("some_avg10_pct")
    if (available_pct < 5 and (full is not None and full > 1 or
                               some is not None and some > 10)):
        return "PRESSURE_LIKELY"
    if available_pct >= 15 and (full is None or full < 0.1) and (
            some is None or some < 1):
        return "NO_CURRENT_PRESSURE_SIGNAL"
    return "INCONCLUSIVE"


def collect() -> dict[str, object]:
    mem = read_memory_info()
    try:
        psi = read_pressure()
    except (OSError, ValueError):
        psi = {}
    try:
        arc = read_arc()
    except (OSError, ValueError):
        arc = {"state": "UNVERIFIED"}
    try:
        events = read_memory_events()
    except (OSError, ValueError):
        events = {"state": "UNVERIFIED"}
    result: dict[str, object] = {
        "schema": "nabla-truenas-memory-pressure/v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mem_total_bytes": mem["MemTotal"],
        "mem_available_bytes": mem["MemAvailable"],
        "mem_available_pct": round(100 * mem["MemAvailable"] / mem["MemTotal"], 2),
        "swap_used_bytes": mem["SwapTotal"] - mem["SwapFree"],
        "memory_psi": psi,
        "zfs_arc": arc,
        "cgroup_events_cumulative": events,
        "docker": docker_snapshot(),
        "assessment": assess(mem, psi, events),
        "note": "cumulative OOM counters need two samples to infer new kills; low free alone does not mean OOM",
    }
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true", required=True)
    args = p.parse_args(argv)
    try:
        report = collect()
    except (OSError, ValueError, ZeroDivisionError) as error:
        print(json.dumps({"assessment": "UNVERIFIED", "error_class": type(error).__name__}))
        return 2
    print(json.dumps(report, sort_keys=True, indent=2))
    return 1 if report["assessment"] == "PRESSURE_LIKELY" else (
        2 if report["assessment"] == "INCONCLUSIVE" else 0
    )


if __name__ == "__main__":
    sys.exit(main())
