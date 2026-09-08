#!/usr/bin/env bash
set -euo pipefail

NETWORK_NAME="${FASTAPI_SAMPLE_OBSERVER_NETWORK:-sample-observer}"
NETWORK_LABEL="com.nabla.role"
NETWORK_ROLE="fastapi-sample-observer"
NETWORK_CONTRACT="v2"
MODE="${1:---prepare}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] ||
  fail "run with sudo so Docker network creation is deterministic"

case "${MODE}" in
  --prepare | --recreate) ;;
  *)
    fail "usage: sudo bash scripts/truenas/prepare-sample-observer-network.sh [--prepare|--recreate]"
    ;;
esac

for command in docker python3 ip jq mktemp; do
  command -v "${command}" >/dev/null 2>&1 ||
    fail "${command} is required"
done

if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  role="$(
    docker network inspect "${NETWORK_NAME}" |
      jq -r '.[0].Labels["com.nabla.role"] // empty'
  )"
  contract="$(
    docker network inspect "${NETWORK_NAME}" |
      jq -r '.[0].Labels["com.nabla.observer-contract"] // empty'
  )"
  [[ "${role}" == "${NETWORK_ROLE}" ]] ||
    fail "existing ${NETWORK_NAME} is not owned by this repository (label ${NETWORK_LABEL}=${role:-<missing>})"

  if [[ "${contract}" == "${NETWORK_CONTRACT}" && "${MODE}" != "--recreate" ]]; then
    docker network inspect "${NETWORK_NAME}" |
      jq -r '
        .[0] |
        {
          name: .Name,
          subnet: (.IPAM.Config[0].Subnet // ""),
          ip_range: (.IPAM.Config[0].IPRange // ""),
          gateway: (.IPAM.Config[0].Gateway // ""),
          observer_ip: (.Labels["com.nabla.observer-ip"] // ""),
          contract: (.Labels["com.nabla.observer-contract"] // "")
        }
      '
    exit 0
  fi

  attached="$(
    docker network inspect "${NETWORK_NAME}" |
      jq '.[0].Containers // {} | length'
  )"
  if [[ "${attached}" != "0" ]]; then
    fail "existing ${NETWORK_NAME} uses obsolete/forced-recreate contract and still has ${attached} attached container(s); remove the failed FastAPI Sample container first, then rerun with --recreate"
  fi

  if [[ "${MODE}" != "--recreate" ]]; then
    fail "existing ${NETWORK_NAME} uses obsolete observer contract ${contract:-<missing>}; rerun with --recreate after detaching/removing FastAPI Sample"
  fi

  docker network rm "${NETWORK_NAME}" >/dev/null
  printf 'Removed obsolete observer network %s before safe recreation\n' "${NETWORK_NAME}"
fi

mapfile -t network_ids < <(docker network ls -q)
[[ "${#network_ids[@]}" -gt 0 ]] ||
  fail "Docker returned no networks to inspect"

docker_tmp="$(mktemp)"
route_tmp="$(mktemp)"
trap 'rm -f "${docker_tmp}" "${route_tmp}"' EXIT

docker network inspect "${network_ids[@]}" >"${docker_tmp}"
ip -j -4 route show table all >"${route_tmp}"

selection="$(
  python3 - "${docker_tmp}" "${route_tmp}" <<'PY'
import ipaddress
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    docker_data = json.load(handle)

with open(sys.argv[2], encoding="utf-8") as handle:
    route_data = json.load(handle)

used = []
for network in docker_data:
    for cfg in network.get("IPAM", {}).get("Config") or []:
        subnet = cfg.get("Subnet")
        if not subnet:
            continue
        try:
            used.append(("docker:" + network.get("Name", "?"), ipaddress.ip_network(subnet, strict=False)))
        except ValueError:
            pass

for route in route_data:
    dst = route.get("dst")
    if not dst or dst == "default":
        continue
    try:
        net = ipaddress.ip_network(dst, strict=False)
    except ValueError:
        continue

    # Host /32 routes do not consume a Docker bridge subnet. Broader connected,
    # VPN, policy-routing and static routes must be respected.
    if net.prefixlen < 32:
        used.append(("route:" + dst, net))

candidates = [
    "10.254.255.0/28",
    "10.254.254.0/28",
    "10.253.255.0/28",
    "10.253.254.0/28",
    "192.168.254.0/28",
    "192.168.253.0/28",
    "172.31.254.0/28",
    "172.30.254.0/28",
]

chosen = None
for raw in candidates:
    candidate = ipaddress.ip_network(raw)
    conflicts = [name for name, net in used if candidate.overlaps(net)]
    if not conflicts:
        chosen = candidate
        break

if chosen is None:
    print("No predefined private /28 is free.", file=sys.stderr)
    for raw in candidates:
        candidate = ipaddress.ip_network(raw)
        conflicts = [f"{name}={net}" for name, net in used if candidate.overlaps(net)]
        print(f"  {candidate}: {', '.join(conflicts) or 'unknown conflict'}", file=sys.stderr)
    raise SystemExit(2)

base = int(chosen.network_address)
gateway = ipaddress.ip_address(base + 1)
ip_range = ipaddress.ip_network(f"{ipaddress.ip_address(base + 8)}/29", strict=True)
observer = ipaddress.ip_address(base + 9)
reserved_offsets = (8, 10, 11, 12, 13, 14)

print(f"SUBNET={chosen}")
print(f"GATEWAY={gateway}")
print(f"IP_RANGE={ip_range}")
print(f"OBSERVER_IP={observer}")
for offset in reserved_offsets:
    print(f"RESERVE_{offset}={ipaddress.ip_address(base + offset)}")
PY
)"

eval "${selection}"

printf 'Selected non-overlapping observer network: subnet=%s ip_range=%s observer_ip=%s\n' \
  "${SUBNET}" "${IP_RANGE}" "${OBSERVER_IP}"

docker network create \
  --driver bridge \
  --subnet "${SUBNET}" \
  --gateway "${GATEWAY}" \
  --ip-range "${IP_RANGE}" \
  # Docker IPAM proved that the first address of the nested /29 (.8) is
  # allocatable, so reserve it explicitly; .9 is the only intended container IP.
  --aux-address "reserve8=${RESERVE_8}" \
  --aux-address "reserve10=${RESERVE_10}" \
  --aux-address "reserve11=${RESERVE_11}" \
  --aux-address "reserve12=${RESERVE_12}" \
  --aux-address "reserve13=${RESERVE_13}" \
  --aux-address "reserve14=${RESERVE_14}" \
  --label "${NETWORK_LABEL}=${NETWORK_ROLE}" \
  --label "com.nabla.observer-contract=${NETWORK_CONTRACT}" \
  --label "com.nabla.observer-ip=${OBSERVER_IP}" \
  "${NETWORK_NAME}" >/dev/null

docker network inspect "${NETWORK_NAME}" |
  jq -e --arg observer "${OBSERVER_IP}" '
    .[0] |
    .Labels["com.nabla.role"] == "fastapi-sample-observer" and
    .Labels["com.nabla.observer-contract"] == "v2" and
    .Labels["com.nabla.observer-ip"] == $observer and
    (.IPAM.Config[0].Subnet | length > 0) and
    (.IPAM.Config[0].IPRange | length > 0)
  ' >/dev/null ||
  fail "created observer network failed its ownership/IPAM contract"

printf 'OK: %s prepared; FastAPI Sample will receive the only allocatable observer address %s\n' \
  "${NETWORK_NAME}" "${OBSERVER_IP}"
