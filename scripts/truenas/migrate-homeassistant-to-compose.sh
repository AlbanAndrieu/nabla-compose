#!/usr/bin/env bash
# Cut Home Assistant over from the native TrueNAS App "home-assistant" to the
# repository-managed Custom App "homeassistant" (apps/homeassistant/compose.yml).
#
#   sudo bash scripts/truenas/migrate-homeassistant-to-compose.sh --check
#   sudo NABLA_RUNTIME_CHANGE_APPROVED=yes bash scripts/truenas/migrate-homeassistant-to-compose.sh --apply
#   sudo NABLA_RUNTIME_CHANGE_APPROVED=yes bash scripts/truenas/migrate-homeassistant-to-compose.sh --rollback
#
# --check changes nothing. --apply snapshots the Home Assistant dataset, stops
# the native App, creates/updates the Custom App on the same data and LAN port,
# then waits for HTTP 200; on failure it rolls back automatically. The native
# App and its data are never deleted. The recorder must already use the shared
# PostgreSQL (runbook 2026-11-04 §6), or the operator accepts a new local
# history with NABLA_HA_RECORDER_ACK=new-history.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"
# shellcheck source=../lib/truenas.sh
source "${SCRIPT_DIR}/../lib/truenas.sh"
# shellcheck source=../lib/app-deploy.sh
source "${SCRIPT_DIR}/../lib/app-deploy.sh"

truenas_repo_provenance "$(git rev-parse --show-toplevel)"

MODE="${1:---check}"
NATIVE_APP_ID="${NABLA_HA_NATIVE_APP_ID:-home-assistant}"
APP_ID="${NABLA_HA_APP_ID:-homeassistant}"
CANONICAL_ROOT="${NABLA_HA_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
DATA_ROOT="${NABLA_HA_DATA_ROOT:-/mnt/cpool/ha}"
HEALTH_URL="${NABLA_HA_HEALTH_URL:-http://172.17.0.24:30103/manifest.json}"
LAN_PORT=30103

case "${MODE}" in
  --check | --apply | --rollback) ;;
  *) fail "usage: sudo bash scripts/truenas/migrate-homeassistant-to-compose.sh [--check|--apply|--rollback]" ;;
esac

app_deploy_canonical_checkout "${CANONICAL_ROOT}" zfs curl
compose_path="${CANONICAL_ROOT}/apps/homeassistant/compose.yml"
app_deploy_compose_validate "${compose_path}"

wait_app_state() {
  local app_id="$1" wanted="$2" timeout_seconds="${3:-300}" deadline
  deadline=$((SECONDS + timeout_seconds))
  while ((SECONDS < deadline)); do
    [[ "$(truenas_app_state "${app_id}")" == "${wanted}" ]] && return 0
    sleep 5
  done
  return 1
}

wait_http_ok() {
  local attempts="${1:-36}"
  local attempt
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    curl -fsS -o /dev/null --max-time 10 "${HEALTH_URL}" && return 0
    sleep 10
  done
  return 1
}

port_holders() {
  docker ps --filter "publish=${LAN_PORT}" --format '{{.Names}}'
}

rollback() {
  warn "rolling back: stopping ${APP_ID}, starting ${NATIVE_APP_ID}"
  if [[ "$(truenas_app_state "${APP_ID}")" == "RUNNING" ]]; then
    truenas_job_compact app.stop "${APP_ID}" || warn "app.stop ${APP_ID} failed; starting ${NATIVE_APP_ID} anyway"
  fi
  truenas_job_compact app.start "${NATIVE_APP_ID}"
  truenas_wait_app_running "${NATIVE_APP_ID}" 600 5 || fail "${NATIVE_APP_ID} did not reach RUNNING; restore from the pre-compose snapshot"
  wait_http_ok 18 || fail "${NATIVE_APP_ID} RUNNING but ${HEALTH_URL} does not answer"
  ok "native App ${NATIVE_APP_ID} serves ${HEALTH_URL} again"
}

section "Current state"
native_state="$(truenas_app_state "${NATIVE_APP_ID}")"
custom_state="$(truenas_app_state "${APP_ID}")"
printf 'native App %s: %s\nCustom App %s: %s\n' "${NATIVE_APP_ID}" "${native_state}" "${APP_ID}" "${custom_state}"
printf 'port %s published by: %s\n' "${LAN_PORT}" "$(port_holders | paste -sd, - || true)"

config="${DATA_ROOT}/config/configuration.yaml"
secrets="${DATA_ROOT}/config/secrets.yaml"
[[ -f "${config}" ]] || fail "missing ${config}: wrong DATA_ROOT, refusing to start Home Assistant on an empty config"
[[ -d "${DATA_ROOT}/media" ]] || warn "${DATA_ROOT}/media is missing; Docker would create it owned by root"

dataset="$(zfs list -H -o name,mountpoint 2>/dev/null | awk -v m="${DATA_ROOT}" '$2 == m {print $1}')"
printf 'dataset mounted on %s: %s\n' "${DATA_ROOT}" "${dataset:-none}"

recorder="unknown"
if grep -Eq '^[[:space:]]*db_url:[[:space:]]*!secret[[:space:]]+recorder_db_url' "${config}" &&
  [[ -f "${secrets}" ]] &&
  grep -Eq '^recorder_db_url:.*@172\.17\.0\.24:5432/homeassistant' "${secrets}"; then
  recorder="shared-postgres"
elif grep -Eq '^[[:space:]]*recorder:' "${config}"; then
  recorder="other-database"
else
  recorder="default-sqlite"
fi
printf 'recorder: %s\n' "${recorder}"
# trusted_proxies holds addresses, never secrets: show them for the reverse-proxy check.
printf 'http.trusted_proxies (Cloudflare Tunnel and Traefik must be listed):\n'
awk '/^http:/{f=1; next} f && /^[^[:space:]#]/{f=0} f && /trusted_proxies|^[[:space:]]+-[[:space:]]/' "${config}" || true
bash scripts/truenas/bootstrap-homeassistant-postgres.sh --check || warn "shared PostgreSQL role/database homeassistant not ready"

case "${MODE}" in
  --check)
    printf 'homeassistant_migration_preflight=verified\nhomeassistant_migration_mutations=0\n'
    exit 0
    ;;
  --rollback)
    [[ "${NABLA_RUNTIME_CHANGE_APPROVED:-}" == "yes" ]] ||
      fail "set NABLA_RUNTIME_CHANGE_APPROVED=yes to roll back"
    rollback
    exit 0
    ;;
esac

section "Apply"
[[ "${NABLA_RUNTIME_CHANGE_APPROVED:-}" == "yes" ]] ||
  fail "set NABLA_RUNTIME_CHANGE_APPROVED=yes after a reviewed --check preflight"
if [[ "${recorder}" != "shared-postgres" && "${NABLA_HA_RECORDER_ACK:-}" != "new-history" ]]; then
  fail "recorder=${recorder}: migrate it to the shared PostgreSQL first (runbook 2026-11-04 §6) or set NABLA_HA_RECORDER_ACK=new-history"
fi
[[ -n "${dataset}" ]] ||
  fail "no dataset is mounted exactly on ${DATA_ROOT}: take a verified snapshot by hand before migrating"

snapshot="${dataset}@pre-compose-$(date -u +%Y%m%dT%H%M%SZ)"
zfs snapshot -r "${snapshot}"
ok "snapshot ${snapshot}"

if [[ "${native_state}" != "STOPPED" && "${native_state}" != "MISSING" ]]; then
  truenas_job_compact app.stop "${NATIVE_APP_ID}"
  wait_app_state "${NATIVE_APP_ID}" STOPPED 300 || fail "${NATIVE_APP_ID} did not stop; nothing else changed"
fi
holders="$(port_holders || true)"
if [[ -n "${holders}" ]]; then
  rollback
  fail "port ${LAN_PORT} still published by ${holders}; migration aborted"
fi

# Subshell: a fail inside the shared deployer must still reach the rollback.
if ! (app_deploy_reconcile "${APP_ID}" "${compose_path}" 900) || ! wait_http_ok 36; then
  rollback
  fail "${APP_ID} did not answer on ${HEALTH_URL}; native App restored"
fi
ok "${APP_ID} serves ${HEALTH_URL}; ${NATIVE_APP_ID} stays STOPPED for rollback"
printf 'Next: check history, integrations, ha.albandrieu.com and homeassistant.int.albandrieu.com.\n'
printf 'Delete %s only after an observation period and explicit approval.\n' "${NATIVE_APP_ID}"
