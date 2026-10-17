#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/truenas.sh
source "${SCRIPT_DIR}/../lib/truenas.sh"

MODE="${1:---check}"
TARGET_IPV4_BASE="${TRUENAS_DOCKER_IPV4_BASE:-10.200.0.0/16}"
TARGET_IPV4_SIZE="${TRUENAS_DOCKER_IPV4_SIZE:-24}"
WAIT_SECONDS="${TRUENAS_DOCKER_IPAM_WAIT_SECONDS:-300}"
POST_BOOT_WAIT_SECONDS="${TRUENAS_DOCKER_POST_BOOT_WAIT_SECONDS:-900}"
POST_BOOT_HEARTBEAT_SECONDS="${TRUENAS_DOCKER_POST_BOOT_HEARTBEAT_SECONDS:-60}"
DOCKER_CLI_TIMEOUT="${TRUENAS_DOCKER_CLI_TIMEOUT_SECONDS:-30}"
EXPECTED_BR0_CIDR="${TRUENAS_EXPECTED_BR0_CIDR:-172.17.0.24/24}"
OBSERVER_NETWORK="${FASTAPI_SAMPLE_OBSERVER_NETWORK:-sample-observer}"
OBSERVER_SUBNET="${FASTAPI_SAMPLE_OBSERVER_SUBNET:-10.254.255.0/28}"
KNOWN_CIDRS="${TRUENAS_DOCKER_KNOWN_CIDRS:-172.17.0.0/24 10.20.0.0/24 10.10.10.1/32 10.0.3.0/24 192.168.39.0/24 192.168.122.0/24 10.254.255.0/28 82.66.4.0/24}"

# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

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

runtime_snapshot() {
  local service_state status
  service_state="$(systemctl is-active docker 2>/dev/null || true)"
  status="$(truenas_docker_status || true)"
  printf '%s %s\n' "${service_state:-unknown}" "${status:-UNKNOWN}"
}

wait_runtime_ready() {
  local wait_seconds="$1" deadline started service_state status current last="" next_heartbeat
  [[ "${POST_BOOT_HEARTBEAT_SECONDS}" =~ ^[1-9][0-9]*$ ]] ||
    fail "TRUENAS_DOCKER_POST_BOOT_HEARTBEAT_SECONDS must be a positive integer"
  started="${SECONDS}"
  deadline=$((SECONDS + wait_seconds))
  next_heartbeat="${SECONDS}"
  while ((SECONDS < deadline)); do
    read -r service_state status < <(runtime_snapshot)
    current="${service_state}/${status}"
    if [[ "${current}" != "${last}" ]] || ((SECONDS >= next_heartbeat)); then
      printf '  Docker boot convergence: elapsed=%ss service=%s middleware=%s\n' \
        "$((SECONDS - started))" "${service_state}" "${status}"
      last="${current}"
      next_heartbeat=$((SECONDS + POST_BOOT_HEARTBEAT_SECONDS))
    fi

    if [[ "${service_state}" == "active" && "${status}" == "RUNNING" ]]; then
      timeout "${DOCKER_CLI_TIMEOUT}" docker info \
        --format 'Server={{.ServerVersion}} Containers={{.Containers}} Running={{.ContainersRunning}}' \
        >/dev/null ||
        fail "Docker reports active/RUNNING but docker info did not respond within ${DOCKER_CLI_TIMEOUT}s"
      printf '  Docker boot convergence completed after %ss.\n' "$((SECONDS - started))"
      return 0
    fi

    case "${status}" in
      FAILED | MIGRATION_FAILED | UNCONFIGURED)
        fail "TrueNAS docker.status entered terminal state ${status}"
        ;;
    esac
    sleep 5
  done

  read -r service_state status < <(runtime_snapshot)
  fail "Docker did not converge within ${wait_seconds}s: service=${service_state} middleware=${status}"
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

if [[ "${MODE}" == "--post-reboot-check" ]]; then
  printf 'Waiting for post-reboot Docker initialization (timeout=%ss)...\n' \
    "${POST_BOOT_WAIT_SECONDS}"
  printf '%s\n' \
    'NOTE: this cold-start convergence can legitimately take several minutes even when every TrueNAS App is STOPPED.' \
    '      Docker still has to reopen overlay2 and reload image/layer, stopped-container, network and IPAM metadata before its API and middleware status become ready.' \
    '      2026-10-03 observed baseline on this host: 764 images, 7408 overlay2 directories and about 525 GiB under /mnt/.ix-apps/docker; >10 min convergence was observed.' \
    '      No App is started by this wait. Do not restart Docker/containerd or prune storage while the reboot transaction is active.'
  wait_runtime_ready "${POST_BOOT_WAIT_SECONDS}"
fi

if midclt call app.query >"${app_inventory}" 2>/dev/null; then
  jq -r 'group_by(.state) | map({state:.[0].state,count:length})' "${app_inventory}"
else
  printf 'WARN: app.query failed; application inventory unavailable\n'
  printf '[]\n' >"${app_inventory}"
fi
printf 'apps=%s\n' "${app_inventory}"

network_ids_raw="$(
  timeout "${DOCKER_CLI_TIMEOUT}" docker network ls -q
)" || fail "docker network ls timed out after ${DOCKER_CLI_TIMEOUT}s"
if [[ -n "${network_ids_raw}" ]]; then
  mapfile -t network_ids <<<"${network_ids_raw}"
else
  network_ids=()
fi
if (("${#network_ids[@]}")); then
  timeout "${DOCKER_CLI_TIMEOUT}" docker network inspect "${network_ids[@]}"     >"${network_inventory}" ||
    fail "docker network inspect timed out after ${DOCKER_CLI_TIMEOUT}s"
else
  printf '[]\n' >"${network_inventory}"
fi
printf 'networks=%s count=%s\n' "${network_inventory}" "${#network_ids[@]}"
ip -j -4 route show table all >"${routes_file}"

python3 "${SCRIPT_DIR}/check-docker-address-pool.py" \
  "${TARGET_IPV4_BASE}" "${TARGET_IPV4_SIZE}" "${KNOWN_CIDRS}" \
  "${routes_file}" "${network_inventory}" "${current_target}"

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
  status="$(truenas_docker_status || true)"
  [[ "${service_state}" == "active" ]] ||
    fail "docker.service is ${service_state:-unknown}, expected active"
  [[ "${status}" == "RUNNING" ]] ||
    fail "TrueNAS docker.status is ${status:-UNKNOWN}, expected RUNNING"
  timeout "${DOCKER_CLI_TIMEOUT}" docker info     --format 'Server={{.ServerVersion}} Containers={{.Containers}} Running={{.ContainersRunning}}' ||
    fail "docker info timed out after ${DOCKER_CLI_TIMEOUT}s"
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
wait_runtime_ready "${WAIT_SECONDS}"

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
