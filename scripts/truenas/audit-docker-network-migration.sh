#!/usr/bin/env bash
set -euo pipefail

TARGET_IPV4_BASE="${TRUENAS_DOCKER_IPV4_BASE:-10.200.0.0/16}"
LEGACY_IPV4_BASE="${TRUENAS_DOCKER_LEGACY_IPV4_BASE:-172.16.0.0/12}"
PROTECTED_NETWORKS="${TRUENAS_DOCKER_PROTECTED_NETWORKS:-intranet traefik_network sample-observer nabla-security secrets-backend}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${1:---check}" == "--check" ]] ||
  fail "usage: sudo bash scripts/truenas/audit-docker-network-migration.sh --check"
[[ "${EUID}" -eq 0 ]] || fail "run as root on TrueNAS"

for command in docker jq python3 date; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

umask 077
timestamp="$(date +%Y%m%d-%H%M%S)"
report="/tmp/truenas-docker-network-audit-${timestamp}.json"

mapfile -t ids < <(docker network ls -q)
if ((${#ids[@]})); then
  docker network inspect "${ids[@]}" >"${report}"
else
  printf '[]\n' >"${report}"
fi

printf 'TrueNAS Docker network migration audit\n'
printf 'target=%s legacy=%s\n' "${TARGET_IPV4_BASE}" "${LEGACY_IPV4_BASE}"
printf 'protected=%s\n' "${PROTECTED_NETWORKS}"
printf 'report=%s\n\n' "${report}"

python3 - "${TARGET_IPV4_BASE}" "${LEGACY_IPV4_BASE}" "${PROTECTED_NETWORKS}" "${report}" <<'PY'
import ipaddress
import json
import sys
from collections import Counter

target = ipaddress.ip_network(sys.argv[1], strict=False)
legacy = ipaddress.ip_network(sys.argv[2], strict=False)
protected = set(sys.argv[3].split())

with open(sys.argv[4], encoding="utf-8") as handle:
    networks = json.load(handle)

rows = []
counts = Counter()
for item in networks:
    name = item.get("Name", "?")
    labels = item.get("Labels") or {}
    project = labels.get("com.docker.compose.project") or "-"
    endpoints = len(item.get("Containers") or {})
    driver = item.get("Driver") or "?"
    ipv4_subnets = []
    for cfg in item.get("IPAM", {}).get("Config") or []:
        raw = cfg.get("Subnet")
        if not raw:
            continue
        try:
            network = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            continue
        if network.version == 4:
            ipv4_subnets.append(network)

    if name in {"host", "none"}:
        classification = "builtin"
        action = "keep"
    elif name in protected:
        classification = "protected-shared"
        action = "retain; audit consumers before any recreate"
    elif any(network.subnet_of(target) for network in ipv4_subnets):
        classification = "target-pool"
        action = "keep"
    elif any(network.subnet_of(legacy) for network in ipv4_subnets):
        if endpoints:
            classification = "legacy-active"
            action = "owner-specific redeploy; never disconnect live endpoints blindly"
        else:
            classification = "legacy-empty"
            action = "candidate for reviewed owner-specific recreate"
    elif name == "bridge":
        classification = "builtin"
        action = "keep"
    else:
        classification = "other"
        action = "review"

    counts[classification] += 1
    subnet_text = ",".join(str(network) for network in ipv4_subnets) or "-"
    rows.append((classification, name, subnet_text, endpoints, project, driver, action))

print("CLASSIFICATION\tNAME\tIPV4_SUBNET\tENDPOINTS\tPROJECT\tDRIVER\tACTION")
for row in sorted(rows, key=lambda value: (value[0], value[1])):
    print("\t".join(map(str, row)))

print("\nSummary:")
for classification, count in sorted(counts.items()):
    print(f"  {classification}: {count}")

legacy_empty = [row for row in rows if row[0] == "legacy-empty"]
legacy_active = [row for row in rows if row[0] == "legacy-active"]
print(f"\nLegacy migration candidates: active={len(legacy_active)} empty={len(legacy_empty)}")
print("No network was modified or removed.")
PY
