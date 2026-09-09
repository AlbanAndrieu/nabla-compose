#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${SCRUTINY_WORKSTATION_COLLECTOR_CONTAINER:-scrutiny}"
EXPECTED_ENDPOINT="${SCRUTINY_WORKSTATION_API_ENDPOINT:-http://172.17.0.24:31054}"
EXPECTED_HOST_ID="${SCRUTINY_WORKSTATION_HOST_ID:-workstation-albandrieu}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

for command in curl docker grep sed; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

docker inspect "${CONTAINER}" >/dev/null 2>&1 ||
  fail "collector container not found: ${CONTAINER}"

state="$(docker inspect "${CONTAINER}" --format '{{.State.Status}}')"
[[ "${state}" == "running" ]] ||
  fail "${CONTAINER} is not running (state=${state})"

mapfile -t env_lines < <(
  docker inspect "${CONTAINER}" |
    sed -n '/"Env": \[/,/]/{s/^[[:space:]]*"//;s/",\{0,1\}$//;p;}' |
    grep -E '^(COLLECTOR_API_ENDPOINT|COLLECTOR_HOST_ID)=' || true
)

endpoint=""
host_id=""
for line in "${env_lines[@]}"; do
  case "${line}" in
    COLLECTOR_API_ENDPOINT=*) endpoint="${line#COLLECTOR_API_ENDPOINT=}" ;;
    COLLECTOR_HOST_ID=*) host_id="${line#COLLECTOR_HOST_ID=}" ;;
  esac
done

[[ "${endpoint}" == "${EXPECTED_ENDPOINT}" ]] ||
  fail "COLLECTOR_API_ENDPOINT=${endpoint:-<missing>} expected=${EXPECTED_ENDPOINT}"

if [[ -n "${host_id}" && "${host_id}" != "${EXPECTED_HOST_ID}" ]]; then
  fail "COLLECTOR_HOST_ID=${host_id} expected=${EXPECTED_HOST_ID}"
fi

curl -fsS --connect-timeout 3 --max-time 8 "${EXPECTED_ENDPOINT}/api/health" >/dev/null ||
  fail "Scrutiny Web/API is not reachable from workstation at ${EXPECTED_ENDPOINT}"

scan="$(docker exec "${CONTAINER}" smartctl --scan-open 2>&1 || true)"
[[ -n "${scan}" ]] || fail "smartctl sees no devices inside ${CONTAINER}"
printf '%s\n' "${scan}"

printf '✅ workstation Scrutiny collector: container=%s endpoint=%s host_id=%s devices=VISIBLE\n' \
  "${CONTAINER}" "${endpoint}" "${host_id:-<default>}"
