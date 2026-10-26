#!/usr/bin/env python3
"""One-shot, read-only resource evidence mapped to Backstage service identities.

No agent, no continuous scrape, no docker inspect env, no secret output.
Declared entities remain even if Docker/GPU/ZFS observations are unavailable.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
ENTITIES = ROOT / "catalog/generated/entities.json"
IDENTITIES = ROOT / "catalog/generated/identity-map.json"
DOCKER_FORMAT = (
    '{{.ID}}\t{{.Names}}\t{{.Label "com.albandrieu.nabla.entity-ref"}}'
    '\t{{.Label "com.docker.compose.project"}}'
    '\t{{.Label "com.docker.compose.service"}}'
)
MAX_STDOUT = 512 * 1024
MAX_CONTAINERS = 300
RE_REF = re.compile(r"^(component|resource):default/[a-z0-9][a-z0-9-]*$")
RE_ID = re.compile(r"^[a-f0-9]{12,64}$")
RE_NAME = re.compile(r"^[a-zA-Z0-9_.-]{1,110}$")
RE_SOURCE = re.compile(r"^apps/([a-z0-9-]+)/compose\.yml#services/([a-zA-Z0-9_.-]+)$")
UNITS = {"B": 1, "kB": 1000, "MB": 1000**2, "GB": 1000**3,
         "TB": 1000**4, "KiB": 1024, "MiB": 1024**2,
         "GiB": 1024**3, "TiB": 1024**4}


def command(argv: list[str], timeout: int = 18) -> str | None:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode or len(done.stdout) > MAX_STDOUT:
        return None
    return done.stdout


def parse_size(value: str) -> int | None:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)\s*", value)
    if not match or match.group(2) not in UNITS:
        return None
    return int(float(match.group(1)) * UNITS[match.group(2)])


def catalog():
    source = json.loads(ENTITIES.read_text(encoding="utf-8"))
    identity = json.loads(IDENTITIES.read_text(encoding="utf-8"))
    refs = {}
    for entity in source.get("entities", []):
        ref = entity.get("entityRef")
        if entity.get("kind") in ("Component", "Resource") and isinstance(ref, str) and RE_REF.fullmatch(ref):
            refs[ref] = entity.get("metadata", {}).get("title") or entity.get("metadata", {}).get("name", ref)
    mapped: dict[tuple[str, str], set[str]] = defaultdict(set)
    for record in identity.get("mappings", []):
        if record.get("sourceType") != "compose":
            continue
        match = RE_SOURCE.fullmatch(str(record.get("sourceId", "")))
        ref = record.get("entityRef")
        if match and ref in refs:
            mapped[(match.group(1), match.group(2))].add(ref)
    return refs, mapped, source.get("catalogRevision", "unknown")


def docker_containers(mapped, refs):
    out = command(["docker", "ps", "--no-trunc", "--format", DOCKER_FORMAT], 20)
    if out is None:
        return None, [], {}
    discovered = []
    reverse = {}
    for row in out.splitlines()[:MAX_CONTAINERS]:
        parts = row.split("\t")
        if len(parts) != 5:
            continue
        cid, name, direct, project, service = parts
        if not RE_ID.fullmatch(cid) or not RE_NAME.fullmatch(name):
            continue
        choices = set()
        if direct in refs:
            choices.add(direct)
        if not choices:
            logical_project = project.removeprefix("ix-")
            choices = mapped.get((logical_project, service), set())
        ref = next(iter(choices)) if len(choices) == 1 else None
        discovered.append({"id": cid, "name": name, "entityRef": ref})
        reverse[name] = ref
    return discovered, [row["name"] for row in discovered if row["entityRef"] is None], reverse


def memory_stats():
    out = command(["docker", "stats", "--no-stream",
                   "--format", "{{.Name}}\t{{.MemUsage}}"], 22)
    result = {}
    if out is None:
        return None
    for line in out.splitlines()[:MAX_CONTAINERS]:
        parts = line.split("\t")
        if len(parts) != 2 or not RE_NAME.fullmatch(parts[0]):
            continue
        amount = parse_size(parts[1].split("/", 1)[0])
        if amount is not None:
            result[parts[0]] = amount
    return result


def writable_layers():
    out = command(["docker", "ps", "--size",
                   "--format", "{{.Names}}\t{{.Size}}"], 25)
    if out is None:
        return None
    result = {}
    for line in out.splitlines()[:MAX_CONTAINERS]:
        parts = line.split("\t")
        if len(parts) != 2 or not RE_NAME.fullmatch(parts[0]):
            continue
        size = parse_size(parts[1].split("(", 1)[0].strip())
        if size is not None:
            result[parts[0]] = size
    return result


def datasets():
    out = command(["zfs", "list", "-Hp", "-t", "filesystem",
                   "-o", "name,used,mountpoint"], 12)
    if out is None:
        return None
    found = []
    for line in out.splitlines():
        cols = line.split("\t")
        if len(cols) != 3 or not cols[1].isdigit():
            continue
        name, used, mount = cols
        if mount.startswith("/mnt/cpool/") and not ".." in mount.split("/"):
            found.append((mount.rstrip("/"), name, int(used)))
    return sorted(found, reverse=True, key=lambda row: len(row[0]))


def mounted_datasets(containers, zfs):
    # Deliberately omit mount source paths from the published report.
    if zfs is None:
        return None
    result = defaultdict(set)
    ids = [c["id"] for c in containers]
    for start in range(0, len(ids), 20):
        batch = ids[start:start+20]
        out = command(["docker", "inspect", "--format",
                       "{{.Id}}\t{{json .Mounts}}", *batch], 14)
        if out is None:
            continue
        for line in out.splitlines():
            cid, sep, raw = line.partition("\t")
            if not sep or cid not in batch:
                continue
            try:
                mounts = json.loads(raw)
            except (ValueError, TypeError):
                continue
            for entry in mounts if isinstance(mounts, list) else []:
                source = entry.get("Source") if isinstance(entry, dict) else None
                if not isinstance(source, str):
                    continue
                for root, dataset, _used in zfs:
                    if source == root or source.startswith(root + "/"):
                        result[cid].add(dataset)
                        break
    return result


def gpu_processes(containers):
    # GPU can physically live on another host (workstation), in which case
    # TrueNAS evidence MUST NOT be shown as 0 MiB GPU for that service.
    out = command(["nvidia-smi", "--query-compute-apps=pid,used_gpu_memory",
                   "--format=csv,noheader,nounits"], 6)
    if out is None:
        return None
    gpu_bytes = defaultdict(int)
    identified = set()
    for line in out.splitlines()[:300]:
        cols = [c.strip() for c in line.split(",")]
        if len(cols) < 2 or not cols[0].isdigit() or not cols[1].isdigit():
            continue
        pid = int(cols[0])
        try:
            cgroup = Path("/proc") / str(pid) / "cgroup"
            text = cgroup.read_text(encoding="utf-8")[:8192]
        except (OSError, UnicodeError):
            continue
        candidates = [c["id"] for c in containers if c["id"] in text or c["id"][:12] in text]
        if len(candidates) == 1:
            gpu_bytes[candidates[0]] += int(cols[1]) * 1024**2
            identified.add(candidates[0])
    return dict(gpu_bytes)


def host_memory():
    values = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            for key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                if line.startswith(key + ":"):
                    values[key] = int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return {"status": "unverified"}
    if not all(k in values for k in ("MemTotal", "MemAvailable")):
        return {"status": "unverified"}
    return {"status": "observed", "total_bytes": values["MemTotal"],
            "available_bytes": values["MemAvailable"],
            "swap_bytes": max(0, values.get("SwapTotal", 0) - values.get("SwapFree", 0))}


def collect(host: str = "truenas") -> dict[str, object]:
    refs, mapping, revision = catalog()
    containers, unmapped, _names = docker_containers(mapping, refs)
    memory = memory_stats() if containers is not None else None
    layer = writable_layers() if containers is not None else None
    zfs = datasets() if host == "truenas" else None
    mount_map = mounted_datasets(containers, zfs) if containers is not None else None
    gpu = gpu_processes(containers) if containers is not None else None
    by_ref = defaultdict(list)
    for row in containers or []:
        if row["entityRef"]:
            by_ref[row["entityRef"]].append(row)
    refs_to_datasets = defaultdict(set)
    for ref, group in by_ref.items():
        for row in group:
            refs_to_datasets[ref].update((mount_map or {}).get(row["id"], set()))
    dataset_users = defaultdict(set)
    for ref, names in refs_to_datasets.items():
        for name in names:
            dataset_users[name].add(ref)
    zfs_map = {name: used for _mount, name, used in zfs or []}

    result = []
    for ref in sorted(refs):
        group = by_ref.get(ref, [])
        used_mem = [memory[c["name"]] for c in group if memory is not None and c["name"] in memory]
        used_layer = [layer[c["name"]] for c in group if layer is not None and c["name"] in layer]
        gpu_measured = [gpu[c["id"]] for c in group if gpu is not None and c["id"] in gpu]
        dataset_names = sorted(refs_to_datasets.get(ref, []))
        result.append({
            "entityRef": ref,
            "name": refs[ref],
            "host": host,
            "observed_containers": [c["name"] for c in group],
            "memory": {
                "status": "observed" if group and len(used_mem) == len(group) else "unverified",
                "working_set_bytes": sum(used_mem) if group and len(used_mem) == len(group) else None,
            },
            "gpu": {
                "status": "observed_process_memory" if gpu_measured else "unverified",
                "process_memory_bytes": sum(gpu_measured) if gpu_measured else None,
            },
            "storage": {
                "writable_layer_status": "observed" if group and len(used_layer) == len(group) else "unverified",
                "writable_layer_bytes": sum(used_layer) if group and len(used_layer) == len(group) else None,
                "datasets_status": "observed" if zfs is not None and mount_map is not None else "unverified",
                "datasets": [{
                    "name": name,
                    "used_bytes_including_children": zfs_map[name],
                    "shared_by_services": len(dataset_users[name]) > 1,
                } for name in dataset_names if name in zfs_map],
            },
        })
    return {
        "schema": "nabla-service-resources/v1",
        "catalog_revision": revision,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_host": host,
        "host_memory": host_memory(),
        "collection": {
            "docker": "observed" if containers is not None else "unverified",
            "gpu": "observed_host" if gpu is not None else "unavailable",
            "storage": "observed_host" if zfs is not None else "unavailable",
            "sample": "one_shot_not_peak",
        },
        "unmapped_container_count": len(unmapped),
        "services": result,
    }


def write_private(path: Path, payload: dict[str, object]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("report already exists")
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("private report directory unavailable")
    info = parent.stat(follow_symlinks=False)
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("private report directory requires owner mode 0700")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--host", choices=("truenas", "workstation"), default="truenas")
    parser.add_argument("--output", type=Path, help="nonexistent file under owner-owned 0700 dir")
    args = parser.parse_args()
    try:
        snapshot = collect(args.host)
        if args.output is not None:
            write_private(args.output, snapshot)
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({"schema": "nabla-service-resources/v1",
                          "status": "unverified", "error_class": type(error).__name__}))
        return 2
    print(json.dumps(snapshot, indent=2, sort_keys=True, allow_nan=False))
    return 0 if snapshot["collection"]["docker"] == "observed" else 2


if __name__ == "__main__":
    sys.exit(main())
