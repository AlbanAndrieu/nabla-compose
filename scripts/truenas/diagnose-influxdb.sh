#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
APP_ID="${INFLUXDB_APP_ID:-influxdb}"
CONTAINER="${INFLUXDB_CONTAINER:-influxdb}"
HOST_URL="${INFLUXDB_HOST_URL:-http://127.0.0.1:31055}"
INTERNAL_URL="${INFLUXDB_INTERNAL_URL:-http://127.0.0.1:8086}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
--check) ;;
*) fail "usage: sudo bash scripts/truenas/diagnose-influxdb.sh --check" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run with sudo"

for command in curl docker jq midclt; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

failures=0

printf '==> TrueNAS InfluxDB app\n'
app_json="$(midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]")"
if [[ "$(jq 'length' <<<"${app_json}")" -ne 1 ]]; then
  printf '❌ TrueNAS app %s is missing\n' "${APP_ID}" >&2
  failures=$((failures + 1))
else
  jq '.[0] | {id,state,active_workloads}' <<<"${app_json}"
fi

printf '\n==> Docker InfluxDB runtime\n'
if ! docker inspect "${CONTAINER}" >/dev/null 2>&1; then
  printf '❌ container %s is missing\n' "${CONTAINER}" >&2
  failures=$((failures + 1))
else
  docker inspect "${CONTAINER}" |
    jq '.[0] | {
      name: .Name,
      state: .State.Status,
      health: (.State.Health.Status // "none"),
      restarts: .RestartCount,
      started: .State.StartedAt,
      exit_code: .State.ExitCode,
      error: .State.Error,
      ports: .NetworkSettings.Ports
    }'

  state="$(docker inspect "${CONTAINER}" --format '{{.State.Status}}')"
  [[ "${state}" == "running" ]] || failures=$((failures + 1))
fi

probe() {
  local label="$1"
  local url="$2"
  local code

  code="$(
    curl -sS       --connect-timeout 3       --max-time 8       -o /tmp/nabla-influx-health.json       -w '%{http_code}'       "${url}/health" 2>/dev/null || true
  )"

  if [[ "${code}" != "200" ]]; then
    printf '❌ %s health returned HTTP %s from %s/health\n'       "${label}" "${code:-000}" "${url}" >&2
    failures=$((failures + 1))
    return
  fi

  printf '✅ %s health HTTP 200\n' "${label}"
  cat /tmp/nabla-influx-health.json
  printf '\n'
}

printf '\n==> Host-published InfluxDB health\n'
probe host "${HOST_URL}"

if docker inspect "${CONTAINER}" >/dev/null 2>&1; then
  printf '\n==> Container-internal InfluxDB health\n'
  if docker exec "${CONTAINER}"     curl -fsS --connect-timeout 3 --max-time 8 "${INTERNAL_URL}/health"; then
    printf '\n✅ container-internal health reachable\n'
  else
    printf '❌ container-internal health is not reachable\n' >&2
    failures=$((failures + 1))
  fi

  printf '\n==> Recent InfluxDB logs\n'
  docker logs --tail 100 "${CONTAINER}" 2>&1 || true
fi

rm -f /tmp/nabla-influx-health.json

[[ "${failures}" -eq 0 ]] ||
  fail "InfluxDB runtime diagnosis found ${failures} issue(s)"

printf '✅ InfluxDB runtime converged\n'
