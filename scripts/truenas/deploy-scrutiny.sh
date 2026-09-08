#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
INFLUX_APP_ID="${INFLUXDB_APP_ID:-influxdb}"
SCRUTINY_APP_ID="${SCRUTINY_APP_ID:-scrutiny}"
SCRUTINY_SECRET_FILE="${SCRUTINY_SECRET_FILE:-/mnt/cpool/scrutiny/.env.secrets}"
WAIT_ATTEMPTS="${SCRUTINY_WAIT_ATTEMPTS:-60}"
WAIT_DELAY="${SCRUTINY_WAIT_DELAY_SECONDS:-2}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *)
    fail "usage: sudo bash scripts/truenas/deploy-scrutiny.sh [--check|--apply]"
    ;;
esac

[[ "${EUID}" -eq 0 ]] ||
  fail "run with sudo so runtime datasets and secrets are validated consistently"

for command in docker git jq midclt curl grep stat install; do
  command -v "${command}" >/dev/null 2>&1 ||
    fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

if [[ "${MODE}" == "--apply" ]]; then
  [[ "${SCRUTINY_CUTOVER_APPROVED:-0}" == "1" ]] ||
    fail "set SCRUTINY_CUTOVER_APPROVED=1 after snapshot/history/token review"

  install -d -m 0750     /mnt/cpool/influxdb/data     /mnt/cpool/influxdb/config     /mnt/cpool/scrutiny/config
fi

for path in   /mnt/cpool/influxdb/data   /mnt/cpool/influxdb/config   /mnt/cpool/scrutiny/config; do
  [[ -d "${path}" ]] || fail "missing runtime directory: ${path}"
done

[[ -f "${SCRUTINY_SECRET_FILE}" && -s "${SCRUTINY_SECRET_FILE}" ]] ||
  fail "missing Scrutiny secret file: ${SCRUTINY_SECRET_FILE}"

secret_mode="$(stat -c '%a' "${SCRUTINY_SECRET_FILE}")"
[[ "${secret_mode}" == "600" ]] ||
  fail "${SCRUTINY_SECRET_FILE} must be mode 0600 (current: ${secret_mode})"

grep -q '^SCRUTINY_WEB_INFLUXDB_TOKEN=.' "${SCRUTINY_SECRET_FILE}" ||
  fail "SCRUTINY_WEB_INFLUXDB_TOKEN is missing from ${SCRUTINY_SECRET_FILE}"

docker network inspect intranet >/dev/null 2>&1 ||
  fail "external Docker network intranet is missing"

docker compose   -f apps/influxdb/compose.yml   config   --quiet   --no-interpolate   --no-env-resolution

docker compose   -f apps/scrutiny/compose.yml   config   --quiet   --no-interpolate   --no-env-resolution

wait_http() {
  local label="$1"
  local url="$2"
  local body=""
  local attempt

  for ((attempt = 1; attempt <= WAIT_ATTEMPTS; attempt++)); do
    if body="$(
      curl --fail --silent --show-error         --connect-timeout 3         --max-time 8         "${url}" 2>/dev/null
    )"; then
      printf '%s\n' "${body}"
      return 0
    fi
    sleep "${WAIT_DELAY}"
  done

  fail "${label} did not become healthy: ${url}"
}

app_state() {
  local app_id="$1"
  midclt call app.query "[[\"id\",\"=\",\"${app_id}\"]]" |
    jq -r '.[0].state // "MISSING"'
}

reconcile_app() {
  local app_id="$1"
  local compose_path="$2"

  if midclt call app.query "[[\"id\",\"=\",\"${app_id}\"]]" |
    jq -e 'length > 0' >/dev/null; then
    printf 'Updating TrueNAS Custom App %s...\n' "${app_id}"
    midclt call -j app.update "${app_id}" "$(
      jq -cn --arg include "${compose_path}" '{
        custom_compose_config: {
          include: [$include]
        }
      }'
    )"
    midclt call -j app.redeploy "${app_id}"
  else
    printf 'Creating TrueNAS Custom App %s...\n' "${app_id}"
    wrapper="$(printf 'include:\n  - %s\n' "${compose_path}")"
    midclt call -j app.create "$(
      jq -cn         --arg app_name "${app_id}"         --arg compose "${wrapper}"         '{
          app_name: $app_name,
          custom_app: true,
          custom_compose_config_string: $compose
        }'
    )"
  fi
}

verify_runtime() {
  local influx_state
  local scrutiny_state
  local influx_payload

  influx_state="$(app_state "${INFLUX_APP_ID}")"
  scrutiny_state="$(app_state "${SCRUTINY_APP_ID}")"

  [[ "${influx_state}" == "RUNNING" ]] ||
    fail "InfluxDB TrueNAS state is ${influx_state}"
  [[ "${scrutiny_state}" == "RUNNING" ]] ||
    fail "Scrutiny TrueNAS state is ${scrutiny_state}"

  influx_payload="$(wait_http "InfluxDB" "http://127.0.0.1:31055/health")"
  jq -e '
    (.status == "pass")
    or (.status == "ok")
    or (.status == "ready")
  ' >/dev/null <<<"${influx_payload}" ||
    fail "InfluxDB health payload is not passing"

  wait_http "Scrutiny" "http://172.17.0.24:31054/api/health" >/dev/null

  for container in scrutiny scrutiny-collector; do
    state="$(
      docker inspect "${container}"         --format '{{.State.Status}}' 2>/dev/null || true
    )"
    [[ "${state}" == "running" ]] ||
      fail "${container} is not running (state=${state:-missing})"
  done

  printf '✅ Scrutiny converged: InfluxDB=RUNNING web=RUNNING collector=RUNNING\n'
}

if [[ "${MODE}" == "--check" ]]; then
  verify_runtime
  exit 0
fi

printf 'NOTE: this helper does not create/restore historical buckets or mint tokens.\n'
printf '      It only performs the reviewed runtime cutover after those prerequisites exist.\n'

reconcile_app "${INFLUX_APP_ID}" "${ROOT}/apps/influxdb/compose.yml"
wait_http "InfluxDB" "http://127.0.0.1:31055/health" >/dev/null

reconcile_app "${SCRUTINY_APP_ID}" "${ROOT}/apps/scrutiny/compose.yml"
wait_http "Scrutiny" "http://172.17.0.24:31054/api/health" >/dev/null

verify_runtime
