#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
TARGET_IPV4_BASE="${TRUENAS_DOCKER_IPV4_BASE:-10.200.0.0/16}"
TARGET_IPV4_SIZE="${TRUENAS_DOCKER_IPV4_SIZE:-24}"
WAIT_SECONDS="${TRUENAS_DOCKER_IPAM_WAIT_SECONDS:-300}"
EXPECTED_BR0_CIDR="${TRUENAS_EXPECTED_BR0_CIDR:-172.17.0.24/24}"
OBSERVER_NETWORK="${FASTAPI_SAMPLE_OBSERVER_NETWORK:-sample-observer}"
OBSERVER_SUBNET="${FASTAPI_SAMPLE_OBSERVER_SUBNET:-10.254.255.0/28}"
KNOWN_CIDRS="${TRUENAS_DOCKER_KNOWN_CIDRS:-172.17.0.0/24 10.20.0.0/24 10.10.10.1/32 10.0.3.0/24 192.168.39.0/24 192.168.122.0/24 10.254.255.0/28 82.66.4.0/24}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

case "${MODE}" in
  --check | --apply | --post-reboot-check) ;;
  *) fail "usage: sudo bash scripts/truenas/migrate-docker-address-pool.sh [--check|--apply|--post-reboot-check]" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run as root on TrueNAS"
for command in midclt jq docker ip python3 systemctl date mktemp; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

umask 077
timestamp="$(date +%Y%m%d-%H%M%S)"
report="/tmp/truenas-docker-ipam-${timestamp}.log"
rollback="/tmp/truenas-docker-ipam-${timestamp}.rollback.json"
network_inventory="/tmp/truenas-docker-ipam-${timestamp}.networks.json"
app_inventory="/tmp/truenas-docker-ipam-${timestamp}.apps.json"
payload_file="/tmp/truenas-docker-ipam-${timestamp}.payload.json"
routes_file="$(mktemp)"
smoke_network=""

cleanup() {
  [[ -z "${smoke_network}" ]] || docker network rm "${smoke_network}" >/dev/null 2>&1 || true
  rm -f "${routes_file}"
}
trap cleanup EXIT
exec > >(tee -a "${report}") 2>&1

printf 'TrueNAS Docker IPAM migration mode=%s target=%s networks=/%s\n' \
  "${MODE}" "${TARGET_IPV4_BASE}" "${TARGET_IPV4_SIZE}"
printf 'report=%s\n' "${report}"

config="$(midclt call docker.config)"
printf '%s\n' "${config}" | jq '{pool,dataset,address_pools,cidr_v6,registry_mirrors}'
printf '%s\n' "${config}" | jq '{address_pools,cidr_v6}' >"${rollback}"
printf 'rollback=%s\n' "${rollback}"

current_target="$(
  jq -r --arg base "${TARGET_IPV4_BASE}" --argjson size "${TARGET_IPV4_SIZE}" '
    ([.address_pools[] | select((.base == $base) and (.size == $size))] | length) == 1 and
    ([.address_pools[] | select(.base | contains(":") | not)] | length) == 1
  ' <<<"${config}"
)"

if midclt call app.query >"${app_inventory}" 2>/dev/null; then
  jq -r 'group_by(.state) | map({state:.[0].state,count:length})' "${app_inventory}"
else
  printf 'WARN: app.query failed; application inventory unavailable\n'
  printf '[]\n' >"${app_inventory}"
fi
printf 'apps=%s\n' "${app_inventory}"

mapfile -t network_ids < <(docker network ls -q)
if ((${#network_ids[@]})); then
  docker network inspect "${network_ids[@]}" >"${network_inventory}"
else
  printf '[]\n' >"${network_inventory}"
fi
printf 'networks=%s count=%s\n' "${network_inventory}" "${#network_ids[@]}"
ip -j -4 route show table all >"${routes_file}"

python3 - "${TARGET_IPV4_BASE}" "${TARGET_IPV4_SIZE}" "${KNOWN_CIDRS}" \
  "${routes_file}" "${network_inventory}" "${current_target}" <<'PY'
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
PY

payload="$(
  jq -c \
    --arg base "${TARGET_IPV4_BASE}" \
    --argjson size "${TARGET_IPV4_SIZE}" '
      {
        address_pools: (
          [{base:$base,size:$size}] +
          [.address_pools[] | select(.base | contains(":"))]
        )
      }
    ' <<<"${config}"
)"
printf '%s\n' "${payload}" | jq . | tee "${payload_file}"
printf 'payload=%s\n' "${payload_file}"

verify_target_config() {
  midclt call docker.config |
    jq -e --arg base "${TARGET_IPV4_BASE}" --argjson size "${TARGET_IPV4_SIZE}" '
      ([.address_pools[] | select((.base == $base) and (.size == $size))] | length) == 1 and
      ([.address_pools[] | select(.base | contains(":") | not)] | length) == 1
    ' >/dev/null ||
    fail "Docker IPv4 address pool drifted from ${TARGET_IPV4_BASE} size=/${TARGET_IPV4_SIZE}"
  printf 'OK: docker.config persists target IPv4 pool %s size=/%s\n' \
    "${TARGET_IPV4_BASE}" "${TARGET_IPV4_SIZE}"
}

verify_runtime_ready() {
  local service_state status
  service_state="$(systemctl is-active docker 2>/dev/null || true)"
  status="$(midclt call docker.status 2>/dev/null | jq -r '.status // "UNKNOWN"' || true)"
  [[ "${service_state}" == "active" ]] ||
    fail "docker.service is ${service_state:-unknown}, expected active"
  [[ "${status}" == "RUNNING" ]] ||
    fail "TrueNAS docker.status is ${status:-UNKNOWN}, expected RUNNING"
  docker info --format 'Server={{.ServerVersion}} Containers={{.Containers}} Running={{.ContainersRunning}}'
  printf 'OK: Docker service and TrueNAS middleware agree on RUNNING\n'
}

verify_br0_contract() {
  ip -4 -o addr show dev br0 |
    awk '{print $4}' |
    grep -Fx -- "${EXPECTED_BR0_CIDR}" >/dev/null ||
    fail "br0 does not carry expected ${EXPECTED_BR0_CIDR}"
  printf 'OK: br0 retains physical LAN address %s\n' "${EXPECTED_BR0_CIDR}"
}

verify_observer_contract() {
  if ! docker network inspect "${OBSERVER_NETWORK}" >/dev/null 2>&1; then
    printf 'WARN: protected observer network %s is absent; verify FastAPI observer separately\n' \
      "${OBSERVER_NETWORK}"
    return 0
  fi
  local subnet
  subnet="$(
    docker network inspect "${OBSERVER_NETWORK}" |
      jq -r '.[0].IPAM.Config[]? | select(.Subnet? and (.Subnet|contains(":")|not)) | .Subnet' |
      head -1
  )"
  [[ "${subnet}" == "${OBSERVER_SUBNET}" ]] ||
    fail "${OBSERVER_NETWORK} subnet is ${subnet:-unset}, expected ${OBSERVER_SUBNET}"
  printf 'OK: protected observer network remains %s=%s\n' "${OBSERVER_NETWORK}" "${subnet}"
}

verify_default_bridge_in_target() {
  local bridge_subnet
  bridge_subnet="$(
    docker network inspect bridge |
      jq -r '.[0].IPAM.Config[]? | select(.Subnet? and (.Subnet|contains(":")|not)) | .Subnet' |
      head -1
  )"
  [[ -n "${bridge_subnet}" ]] || fail "Docker bridge IPv4 subnet is unavailable"
  python3 - "${TARGET_IPV4_BASE}" "${bridge_subnet}" <<'PY'
import ipaddress
import sys

target = ipaddress.ip_network(sys.argv[1], strict=False)
allocated = ipaddress.ip_network(sys.argv[2], strict=False)
if allocated.version != target.version or not allocated.subnet_of(target):
    raise SystemExit(f"ERROR: Docker bridge uses {allocated}, outside target {target}")
print(f"OK: Docker bridge allocation {allocated} remains inside {target}")
PY
}

printf 'docker.status before:\n'
midclt call docker.status | jq .
printf 'docker.service before: %s\n' "$(systemctl is-active docker 2>/dev/null || true)"

if [[ "${MODE}" == "--post-reboot-check" ]]; then
  [[ "${current_target}" == "true" ]] ||
    fail "post-reboot Docker address pool is not ${TARGET_IPV4_BASE} size=/${TARGET_IPV4_SIZE}"
  verify_target_config
  verify_runtime_ready
  verify_br0_contract
  verify_observer_contract
  verify_default_bridge_in_target
  printf 'Application states after reboot:\n'
  midclt call app.query |
    jq -r 'group_by(.state) | map({state:.[0].state,count:length})'
  printf 'SUCCESS: post-reboot Docker IPAM persistence gate passed.\n'
  exit 0
fi

if [[ "${MODE}" == "--check" ]]; then
  if [[ "${current_target}" == "true" ]]; then
    printf 'OK: target IPv4 address pool is already configured\n'
    verify_target_config
    verify_runtime_ready
    verify_br0_contract
    verify_observer_contract
    verify_default_bridge_in_target
    printf 'READY: configuration is idempotent; use --post-reboot-check after the next normal reboot.\n'
  else
    printf 'READY: reviewed target can be applied with --apply\n'
    printf 'NOTE: TrueNAS will stop Docker, remount ix-apps, restart Docker and request app redeploys.\n'
  fi
  exit 0
fi

if [[ "${current_target}" == "true" ]]; then
  printf 'OK: no address-pool mutation required; already on target\n'
else
  printf 'APPLY: changing default Docker address pool through TrueNAS middleware\n'
  midclt call -j docker.update "${payload}"
fi

printf 'Waiting for Docker service and middleware status to converge...\n'
deadline=$((SECONDS + WAIT_SECONDS))
status="UNKNOWN"
while ((SECONDS < deadline)); do
  service_state="$(systemctl is-active docker 2>/dev/null || true)"
  status="$(midclt call docker.status 2>/dev/null | jq -r '.status // "UNKNOWN"' || true)"
  printf '  docker.service=%s middleware=%s\n' "${service_state:-unknown}" "${status:-UNKNOWN}"
  [[ "${service_state}" == "active" && "${status}" == "RUNNING" ]] && break
  sleep 5
done
[[ "$(systemctl is-active docker 2>/dev/null || true)" == "active" ]] ||
  fail "Docker service did not become active within ${WAIT_SECONDS}s"
[[ "${status}" == "RUNNING" ]] ||
  fail "TrueNAS docker.status did not converge to RUNNING within ${WAIT_SECONDS}s"

verify_target_config
verify_runtime_ready
verify_br0_contract
verify_observer_contract

printf '%s\n' "$(midclt call docker.config)" |
  jq '{pool,dataset,address_pools,cidr_v6}'

smoke_network="nabla-ipam-smoke-${timestamp}"
docker network create --label com.nabla.role=ipam-smoke "${smoke_network}" >/dev/null
smoke_subnet="$(
  docker network inspect "${smoke_network}" |
    jq -r '.[0].IPAM.Config[]? | select(.Subnet? and (.Subnet|contains(":")|not)) | .Subnet' |
    head -1
)"
printf 'default-IPAM smoke subnet=%s\n' "${smoke_subnet}"
python3 - "${TARGET_IPV4_BASE}" "${smoke_subnet}" <<'PY'
import ipaddress
import sys

target = ipaddress.ip_network(sys.argv[1], strict=False)
allocated = ipaddress.ip_network(sys.argv[2], strict=False)
if allocated.version != target.version or not allocated.subnet_of(target):
    raise SystemExit(f"ERROR: Docker allocated {allocated}, outside target {target}")
print(f"OK: Docker allocated {allocated} from {target}")
PY
docker network rm "${smoke_network}" >/dev/null
smoke_network=""

printf 'Application states after Docker/IPAM transition:\n'
midclt call app.query |
  jq -r 'group_by(.state) | map({state:.[0].state,count:length})'

printf 'Legacy 172.16/12 Docker networks intentionally retained for reviewed cleanup:\n'
mapfile -t post_ids < <(docker network ls -q)
if ((${#post_ids[@]})); then
  docker network inspect "${post_ids[@]}" |
    jq -r '.[] | .Name as $name | .IPAM.Config[]? |
      select(.Subnet? and (.Subnet|startswith("172."))) |
      "\($name)\t\(.Subnet)"' |
    sort -k2,2V
fi

printf 'SUCCESS: default Docker IPv4 pool migrated to %s with /%s allocations.\n' \
  "${TARGET_IPV4_BASE}" "${TARGET_IPV4_SIZE}"
printf 'Rollback address-pool payload retained at %s\n' "${rollback}"
printf 'Do not prune legacy networks; classify and migrate them separately.\n'
