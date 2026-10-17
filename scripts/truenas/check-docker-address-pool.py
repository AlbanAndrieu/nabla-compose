#!/usr/bin/env python3
"""Validate a target Docker IPv4 pool against known CIDRs, routes and networks (read-only)."""
import ipaddress
import json
import sys

target = ipaddress.ip_network(sys.argv[1], strict=False)
size = int(sys.argv[2])
known_raw = sys.argv[3].split()
current_target = sys.argv[6].lower() == "true"

if target.version != 4:
    raise SystemExit("ERROR: target must be IPv4")
if size <= target.prefixlen or size > 30:
    raise SystemExit(
        f"ERROR: allocation prefix /{size} must be larger than "
        f"{target.prefixlen} and <= 30"
    )

known_conflicts = []
for raw in known_raw:
    network = ipaddress.ip_network(raw, strict=False)
    if network.version == target.version and target.overlaps(network):
        known_conflicts.append(str(network))
if known_conflicts:
    raise SystemExit(
        "ERROR: target overlaps known homelab/network CIDR(s): "
        + ", ".join(known_conflicts)
    )

with open(sys.argv[5], encoding="utf-8") as handle:
    networks = json.load(handle)

# Keep this collection IPv4-only. Docker network inspect also reports the
# fdd0:: IPv6 pool; comparing IPv6 subnet_of() with the IPv4 target previously
# raised TypeError during an idempotent post-migration --check.
docker_networks = []
docker_overlaps = []
for item in networks:
    for cfg in item.get("IPAM", {}).get("Config") or []:
        raw = cfg.get("Subnet")
        if not raw:
            continue
        try:
            network = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            continue
        if network.version != target.version:
            continue
        name = item.get("Name", "?")
        docker_networks.append((name, network))
        if target.overlaps(network):
            docker_overlaps.append((name, network))

if docker_overlaps and not current_target:
    rendered = ", ".join(f"{name}={network}" for name, network in docker_overlaps)
    raise SystemExit("ERROR: target overlaps existing Docker network(s): " + rendered)

if docker_overlaps and current_target:
    outside = [
        f"{name}={network}"
        for name, network in docker_overlaps
        if not network.subnet_of(target)
    ]
    if outside:
        raise SystemExit(
            "ERROR: Docker network crosses target pool boundary: " + ", ".join(outside)
        )
    print(
        "OK: existing Docker allocations inside the configured target pool are expected: "
        + ", ".join(f"{name}={network}" for name, network in docker_overlaps)
    )

with open(sys.argv[4], encoding="utf-8") as handle:
    routes = json.load(handle)

route_conflicts = []
for route in routes:
    dst = route.get("dst")
    if not dst or dst == "default":
        continue
    try:
        network = ipaddress.ip_network(dst, strict=False)
    except ValueError:
        continue
    if network.version != target.version or not target.overlaps(network):
        continue

    dev = route.get("dev", "")
    backed_by_docker = any(
        network.subnet_of(docker_network)
        for _, docker_network in docker_networks
        if docker_network.subnet_of(target)
    )
    docker_device = dev == "docker0" or dev.startswith("br-")
    if current_target and backed_by_docker and docker_device:
        continue
    route_conflicts.append(f"{dst} dev={dev or '?'}")

if route_conflicts:
    raise SystemExit(
        "ERROR: target overlaps non-Docker TrueNAS route(s): "
        + ", ".join(route_conflicts)
    )

count = 1 << (size - target.prefixlen)
print(
    f"OK: {target} is disjoint from known external CIDRs "
    "and non-Docker TrueNAS routes"
)
print(f"OK: target provides {count} possible /{size} Docker network allocations")
