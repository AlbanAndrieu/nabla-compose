#!/usr/bin/env python3
"""Bounded read-only TrueNAS pressure triage. Never log commands or secrets.

Host memory/CPU/IO pressure is independent of Docker working-set estimates.
Stopping Netdata before a sample prevents attributing its historical peak.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

BYTES_PER_KIB = 1024
MAX_DOCKER_BYTES = 512 * 1024
MAX_CONTAINERS = 512
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
SIZE_UNITS = {"B": 1, "kB": 1000, "MB": 1000**2, "GB": 1000**3,
              "TB": 1000**4, "KiB": 1024, "MiB": 1024**2,
              "GiB": 1024**3, "TiB": 1024**4}


def parse_size(raw: str) -> int | None:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)\s*", raw)
    if not match or match.group(2) not in SIZE_UNITS:
        return None
    value = float(match.group(1)) * SIZE_UNITS[match.group(2)]
    return int(value) if math.isfinite(value) else None


def parse_meminfo(text: str) -> dict[str, int]:
    wanted = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}
    fields: dict[str, int] = {}
    for row in text.splitlines():
        match = re.fullmatch(r"([A-Za-z_]+):\s*(\d+)\s+kB\s*", row)
        if match and match.group(1) in wanted:
            fields[match.group(1)] = int(match.group(2)) * BYTES_PER_KIB
    if set(fields) != wanted or fields["MemTotal"] <= 0:
        raise ValueError("missing host memory fields")
    if fields["MemAvailable"] > fields["MemTotal"] or fields["SwapFree"] > fields["SwapTotal"]:
        raise ValueError("invalid host memory fields")
    return fields


def parse_psi(text: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in text.splitlines():
        fields = row.split()
        if not fields or fields[0] not in ("some", "full"):
            continue
        for field in fields[1:]:
            if field.startswith("avg10="):
                try:
                    value = float(field.split("=", 1)[1])
                except ValueError:
                    continue
                if math.isfinite(value) and 0 <= value <= 100:
                    result[fields[0] + "_avg10_pct"] = value
    return result


def parse_vmstat(text: str) -> dict[str, int]:
    targets = ("oom_kill", "pswpin", "pswpout", "pgmajfault")
    result: dict[str, int] = {}
    for row in text.splitlines():
        pair = row.split()
        if len(pair) == 2 and pair[1].isdigit():
            if pair[0] in targets or pair[0].startswith(("pgscan_direct", "allocstall")):
                result[pair[0]] = int(pair[1])
    result["direct_reclaim"] = sum(v for k, v in result.items() if k.startswith("pgscan_direct"))
    result["allocation_stalls"] = sum(v for k, v in result.items() if k.startswith("allocstall"))
    for name in list(result):
        if name.startswith(("pgscan_direct", "allocstall")):
            del result[name]
    return result


def parse_arc(text: str) -> dict[str, int | str]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] in ("size", "c_min", "c"):
            if parts[2].isdigit():
                values[parts[0]] = int(parts[2])
    if "size" not in values or "c_min" not in values:
        return {"state": "UNVERIFIED"}
    return {"state": "OBSERVED", "size_bytes": values["size"],
            "potential_shrink_bytes": max(0, values["size"] - values["c_min"])}


def read_optional(path: str, limit: int = 512 * 1024) -> str | None:
    try:
        with open(path, "r", encoding="ascii", errors="replace") as source:
            content = source.read(limit + 1)
        if len(content) > limit:
            return None
        return content
    except (OSError, UnicodeError):
        return None


def host_sample() -> dict[str, object]:
    raw = read_optional("/proc/meminfo")
    if raw is None:
        raise ValueError("host memory unreadable")
    mem = parse_meminfo(raw)
    psi = {}
    for kind in ("cpu", "memory", "io"):
        data = read_optional(f"/proc/pressure/{kind}", 4096)
        psi[kind] = parse_psi(data) if data is not None else {}
    vm_raw = read_optional("/proc/vmstat")
    arc_raw = read_optional("/proc/spl/kstat/zfs/arcstats")
    return {"at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "memory_available_pct": round(100 * mem["MemAvailable"] / mem["MemTotal"], 2),
            "memory_available_mib": round(mem["MemAvailable"] / 1024**2, 1),
            "memory_total_mib": round(mem["MemTotal"] / 1024**2, 1),
            "swap_used_mib": round((mem["SwapTotal"] - mem["SwapFree"]) / 1024**2, 1),
            "psi": psi,
            "vmstat": parse_vmstat(vm_raw) if vm_raw is not None else {},
            "zfs_arc": parse_arc(arc_raw) if arc_raw is not None else {"state": "UNAVAILABLE"}}


def counter_deltas(before: dict[str, int], after: dict[str, int]) -> dict[str, int | str]:
    result: dict[str, int | str] = {}
    for key in ("oom_kill", "pswpin", "pswpout", "pgmajfault", "direct_reclaim", "allocation_stalls"):
        a, b = before.get(key), after.get(key)
        result[key] = b - a if isinstance(a, int) and isinstance(b, int) and b >= a else "UNVERIFIED"
    return result


def parse_docker_stats(raw: str, top: int) -> dict[str, object]:
    results: list[dict[str, object]] = []
    for line in raw.splitlines():
        if len(results) >= MAX_CONTAINERS:
            break
        try:
            data = json.loads(line)
            name = data.get("Name")
            if not isinstance(name, str) or not SAFE_NAME.fullmatch(name):
                continue
            memory = parse_size(str(data.get("MemUsage", "")).split("/", 1)[0])
            cpu = float(str(data.get("CPUPerc", "")).strip().removesuffix("%"))
            if memory is None or not math.isfinite(cpu) or not 0 <= cpu <= 10000:
                continue
            try:
                mem_limit_pct = float(str(data.get("MemPerc", "")).strip().removesuffix("%"))
                if not math.isfinite(mem_limit_pct) or mem_limit_pct < 0:
                    mem_limit_pct = None
            except ValueError:
                mem_limit_pct = None
            results.append({"name": name, "memory_mib": round(memory / 1024**2, 1),
                            "cpu_pct": round(cpu, 1), "memory_limit_pct": mem_limit_pct})
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
    if not results:
        return {"state": "UNVERIFIED", "containers_sampled": 0,
                "note": "docker stats unavailable or no valid running container samples"}
    by_mem = sorted(results, key=lambda x: x["memory_mib"], reverse=True)
    by_cpu = sorted(results, key=lambda x: x["cpu_pct"], reverse=True)
    return {"state": "OBSERVED", "containers_sampled": len(results),
            "top_memory": by_mem[:top], "top_cpu": by_cpu[:top],
            "netdata_running_in_sample": any("netdata" in x["name"].lower() for x in results),
            "note": "one-shot Docker working set; stopped services omitted; not a historical peak"}


def docker_sample(timeout: int, top: int) -> dict[str, object]:
    try:
        proc = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{json .}}"],
                              capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"state": "UNVERIFIED", "error_class": "DockerUnavailable"}
    if proc.returncode != 0 or len(proc.stdout) > MAX_DOCKER_BYTES:
        return {"state": "UNVERIFIED", "error_class": "DockerStatsUnavailable"}
    return parse_docker_stats(proc.stdout, top)


def assess(last: dict[str, object], deltas: dict[str, int | str]) -> tuple[str, list[str]]:
    psi = last["psi"]
    assert isinstance(psi, dict)
    mem_psi = psi["memory"]
    io_psi = psi["io"]
    cpu_psi = psi["cpu"]
    available = float(last["memory_available_pct"])
    evidence: list[str] = []
    if isinstance(deltas.get("oom_kill"), int) and deltas["oom_kill"] > 0:
        evidence.append("new_host_oom_kill")
    if available < 5 and mem_psi.get("full_avg10_pct", 0) >= 1:
        evidence.append("low_available_with_memory_full_stalls")
    if evidence:
        return "CRITICAL_PRESSURE", evidence
    if available < 10:
        evidence.append("low_memavailable_not_alone_proof_of_oom")
    if mem_psi.get("some_avg10_pct", 0) >= 10:
        evidence.append("memory_reclaim_stalls")
    if io_psi.get("some_avg10_pct", 0) >= 10 or io_psi.get("full_avg10_pct", 0) >= 2:
        evidence.append("io_stalls")
    if cpu_psi.get("some_avg10_pct", 0) >= 50:
        evidence.append("cpu_contention")
    if isinstance(deltas.get("pswpout"), int) and deltas["pswpout"] > 0 and available < 15:
        evidence.append("swap_out_activity")
    if isinstance(deltas.get("allocation_stalls"), int) and deltas["allocation_stalls"] > 0:
        evidence.append("memory_allocation_stalls")
    if evidence:
        return "PRESSURE_SIGNAL", evidence
    if not psi["memory"] or not psi["io"] or not psi["cpu"]:
        return "UNVERIFIED", ["psi_not_available"]
    return "NO_STRONG_CURRENT_SIGNAL", []


def save_report(directory: Path, report: dict[str, object]) -> Path:
    cursor = directory.absolute()
    for candidate in (cursor, *cursor.parents):
        if candidate.is_symlink():
            raise ValueError("symlink directory refused")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    meta = directory.stat()
    if meta.st_uid != os.geteuid() or stat.S_IMODE(meta.st_mode) != 0o700:
        raise ValueError("report directory must be owned by current operator (0700)")
    name = "truenas-pressure-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{os.getpid()}.json"
    destination = directory / name
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(report, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", required=True, action="store_true")
    parser.add_argument("--observe-seconds", type=int, default=10)
    parser.add_argument("--docker-timeout", type=int, default=8)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args(argv)
    if not 0 <= args.observe_seconds <= 60 or not 1 <= args.docker_timeout <= 20 or not 1 <= args.top <= 30:
        parser.error("observe-seconds=0..60 docker-timeout=1..20 top=1..30")
    try:
        first = host_sample()
        time.sleep(args.observe_seconds) if args.observe_seconds else None
        last = host_sample()
    except (OSError, ValueError, ZeroDivisionError) as exc:
        print(json.dumps({"status": "UNVERIFIED", "error_class": type(exc).__name__}))
        return 2
    deltas = counter_deltas(first["vmstat"], last["vmstat"])
    state, signals = assess(last, deltas)
    docker = docker_sample(args.docker_timeout, args.top)
    report = {"schema": "nabla-truenas-pressure/v1", "status": state,
              "at_utc": last["at_utc"], "observe_seconds": args.observe_seconds,
              "memory_available_change_mib": round(last["memory_available_mib"] - first["memory_available_mib"], 1),
              "host": last, "counter_deltas": deltas, "signals": signals,
              "docker": docker, "netdata_hypothesis": "STOPPED_BY_OPERATOR; causality NOT_VERIFIED",
              "limits": "Docker stats excludes stopped containers; single sample does not identify earlier peak or service cause"}
    if args.report_dir:
        try:
            report_path = save_report(args.report_dir, report)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "UNVERIFIED", "report_error_class": type(exc).__name__}))
            return 2
        print("report=" + str(report_path))
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    return {"CRITICAL_PRESSURE": 1, "PRESSURE_SIGNAL": 1,
            "UNVERIFIED": 2, "NO_STRONG_CURRENT_SIGNAL": 0}[state]


if __name__ == "__main__":
    sys.exit(main())
