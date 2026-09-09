#!/usr/bin/env bash
set -euo pipefail

APP_ID="${SCRUTINY_APP_ID:-scrutiny}"
WEB_CONTAINER="${SCRUTINY_WEB_CONTAINER:-scrutiny}"
COLLECTOR_CONTAINER="${SCRUTINY_COLLECTOR_CONTAINER:-scrutiny-collector}"
WEB_URL="${SCRUTINY_WEB_URL:-http://172.17.0.24:31054}"
INFLUX_URL="${SCRUTINY_INFLUX_URL:-http://127.0.0.1:31055}"
SECRET_FILE="${SCRUTINY_SECRET_FILE:-/mnt/cpool/scrutiny/.env.secrets}"
MODE="${1:---check}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check) ;;
  *) fail "usage: sudo bash scripts/truenas/diagnose-scrutiny.sh --check" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run with sudo"
for command in curl docker jq midclt stat grep; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

failures=0

printf '==> TrueNAS Scrutiny app state\n'
app_json="$(midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]")"
if [[ "$(jq 'length' <<<"${app_json}")" -ne 1 ]]; then
  printf '❌ TrueNAS app %s is missing\n' "${APP_ID}" >&2
  failures=$((failures + 1))
else
  jq '.[0] | {id,state,active_workloads}' <<<"${app_json}"
  app_state="$(jq -r '.[0].state // "UNKNOWN"' <<<"${app_json}")"
  if [[ "${app_state}" != "RUNNING" ]]; then
    printf '❌ Scrutiny aggregate state is %s (expected RUNNING)\n' "${app_state}" >&2
    failures=$((failures + 1))
  fi
fi

printf '\n==> Scrutiny secret contract\n'
if [[ ! -s "${SECRET_FILE}" ]]; then
  printf '❌ Scrutiny secret file is missing or empty: %s\n' "${SECRET_FILE}" >&2
  failures=$((failures + 1))
else
  mode="$(stat -c '%a' "${SECRET_FILE}")"
  size="$(stat -c '%s' "${SECRET_FILE}")"
  printf 'secret=%s mode=%s size=%s\n' "${SECRET_FILE}" "${mode}" "${size}"
  [[ "${mode}" == "600" ]] || {
    printf '❌ Scrutiny secret must be mode 0600\n' >&2
    failures=$((failures + 1))
  }
  grep -q '^SCRUTINY_WEB_INFLUXDB_TOKEN=.' "${SECRET_FILE}" || {
    printf '❌ SCRUTINY_WEB_INFLUXDB_TOKEN is missing\n' >&2
    failures=$((failures + 1))
  }
fi

printf '\n==> Shared InfluxDB dependency\n'
if curl -fsS --connect-timeout 3 --max-time 8 "${INFLUX_URL}/health"; then
  printf '\n✅ InfluxDB host health reachable\n'
else
  printf '❌ InfluxDB host health failed: %s/health\n' "${INFLUX_URL}" >&2
  failures=$((failures + 1))
fi

inspect_container() {
  local container="$1"
  local role="$2"

  printf '\n==> %s container\n' "${role}"
  if ! docker inspect "${container}" >/dev/null 2>&1; then
    printf '❌ container %s is missing\n' "${container}" >&2
    failures=$((failures + 1))
    return 1
  fi

  docker inspect "${container}" |
    jq '.[0] | {
      name: .Name,
      state: .State.Status,
      health: (.State.Health.Status // "none"),
      restarts: .RestartCount,
      started: .State.StartedAt,
      exit_code: .State.ExitCode,
      networks: (.NetworkSettings.Networks | keys)
    }'

  state="$(docker inspect "${container}" --format '{{.State.Status}}')"
  health="$(docker inspect "${container}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
  [[ "${state}" == "running" ]] || failures=$((failures + 1))
  if [[ "${health}" == "unhealthy" ]]; then
    failures=$((failures + 1))
  fi
}

if inspect_container "${WEB_CONTAINER}" "Scrutiny web"; then
  printf '\nScrutiny web non-secret InfluxDB configuration:\n'
  docker inspect "${WEB_CONTAINER}" --format '{{range .Config.Env}}{{println .}}{{end}}' |
    grep -E '^SCRUTINY_WEB_INFLUXDB_(HOST|PORT|ORG|BUCKET)=' || true

  if docker exec "${WEB_CONTAINER}" curl -fsS --connect-timeout 3 --max-time 8     http://influxdb:8086/health >/dev/null; then
    printf '✅ Scrutiny web -> influxdb:8086 health\n'
  else
    printf '❌ Scrutiny web cannot reach influxdb:8086\n' >&2
    failures=$((failures + 1))
  fi

  if docker exec "${WEB_CONTAINER}" test -w /opt/scrutiny/config; then
    printf '✅ Scrutiny config directory is writable\n'
  else
    printf '❌ /opt/scrutiny/config is not writable inside web container\n' >&2
    failures=$((failures + 1))
  fi

  if docker exec "${WEB_CONTAINER}" curl -fsS --connect-timeout 3 --max-time 8     http://127.0.0.1:8080/api/health >/dev/null; then
    printf '✅ Scrutiny container-local /api/health\n'
  else
    printf '❌ Scrutiny container-local /api/health failed\n' >&2
    failures=$((failures + 1))
  fi

  printf '\nRecent Scrutiny web logs:\n'
  docker logs --tail 120 "${WEB_CONTAINER}" 2>&1 || true
fi

if inspect_container "${COLLECTOR_CONTAINER}" "Scrutiny collector"; then
  endpoint="$(
    docker inspect "${COLLECTOR_CONTAINER}"       --format '{{range .Config.Env}}{{println .}}{{end}}' |
      sed -n 's/^COLLECTOR_API_ENDPOINT=//p' |
      tail -1
  )"
  printf 'collector_api_endpoint=%s\n' "${endpoint:-missing}"

  scan="$(docker exec "${COLLECTOR_CONTAINER}" smartctl --scan-open 2>/dev/null || true)"
  if [[ -n "${scan}" ]]; then
    printf '✅ collector SMART devices visible:\n%s\n' "${scan}"
  else
    printf '❌ collector smartctl --scan-open returned no devices\n' >&2
    failures=$((failures + 1))
  fi
fi

printf '\n==> Published Scrutiny health\n'
if curl -fsS --connect-timeout 3 --max-time 8 "${WEB_URL}/api/health" >/dev/null; then
  printf '✅ Scrutiny published /api/health reachable\n'
else
  printf '❌ Scrutiny published /api/health failed: %s/api/health\n' "${WEB_URL}" >&2
  failures=$((failures + 1))
fi

if [[ -f /var/log/app_lifecycle.log ]]; then
  printf '\n==> Recent TrueNAS Scrutiny lifecycle failures\n'
  grep -F "for 'scrutiny' app" /var/log/app_lifecycle.log | tail -3 || true
fi

[[ "${failures}" -eq 0 ]] ||
  fail "Scrutiny runtime diagnosis found ${failures} issue(s)"

printf '✅ Scrutiny runtime converged: web/API + InfluxDB + collector SMART\n'
