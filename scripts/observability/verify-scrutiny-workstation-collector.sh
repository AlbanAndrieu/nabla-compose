#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
CONTAINER="${SCRUTINY_WORKSTATION_COLLECTOR_CONTAINER:-scrutiny}"
EXPECTED_ENDPOINT="${SCRUTINY_WORKSTATION_API_ENDPOINT:-http://172.17.0.24:31054}"
EXPECTED_HOST_ID="${SCRUTINY_WORKSTATION_HOST_ID:-albandrieu}"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

case "${MODE}" in
--check | --submit) ;;
*) fail "usage: bash scripts/observability/verify-scrutiny-workstation-collector.sh [--check|--submit]" ;;
esac

for command in curl docker grep; do
    command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

docker inspect "${CONTAINER}" >/dev/null 2>&1 ||
    fail "collector container not found: ${CONTAINER}"

state="$(docker inspect "${CONTAINER}" --format '{{.State.Status}}')"
[[ "${state}" == "running" ]] ||
    fail "${CONTAINER} is not running (state=${state})"

mapfile -t env_lines < <(
    docker inspect "${CONTAINER}" --format '{{range .Config.Env}}{{println .}}{{end}}' |
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

endpoint="${endpoint%/}"
expected_endpoint="${EXPECTED_ENDPOINT%/}"

[[ "${endpoint}" == "${expected_endpoint}" ]] ||
    fail "COLLECTOR_API_ENDPOINT=${endpoint:-<missing>} expected=${expected_endpoint}"
[[ -n "${host_id}" ]] || fail "COLLECTOR_HOST_ID is missing"
[[ "${host_id}" == "${EXPECTED_HOST_ID}" ]] ||
    fail "COLLECTOR_HOST_ID=${host_id} expected=${EXPECTED_HOST_ID}; override SCRUTINY_WORKSTATION_HOST_ID only if this identity is intentional"

curl -fsS --connect-timeout 3 --max-time 8 "${expected_endpoint}/api/health" >/dev/null ||
    fail "Scrutiny Web/API is not reachable from workstation at ${expected_endpoint}"

scan="$(docker exec "${CONTAINER}" smartctl --scan-open 2>&1 || true)"
[[ -n "${scan}" ]] || fail "smartctl sees no devices inside ${CONTAINER}"
printf '%s\n' "${scan}"

if [[ "${MODE}" == "--submit" ]]; then
    docker exec "${CONTAINER}" /opt/scrutiny/bin/scrutiny-collector-metrics run
    printf '✅ workstation SMART submission completed\n'
fi

printf '✅ workstation Scrutiny collector: container=%s endpoint=%s host_id=%s devices=VISIBLE\n' \
    "${CONTAINER}" "${endpoint}" "${host_id}"
