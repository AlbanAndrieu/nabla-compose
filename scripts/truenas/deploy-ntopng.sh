#!/usr/bin/env bash
# Controlled TrueNAS ntopng Custom App deployment. No auto-creation of licenses, secrets or datasets.
set -euo pipefail

MODE="${1:---check}"
case "${MODE}" in
  --check | --apply) ;;
  *) printf 'Usage: sudo bash %s [--check|--apply]\n' "$0" >&2; exit 2 ;;
esac

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"
# shellcheck source=../lib/truenas.sh
source "${SCRIPT_DIR}/../lib/truenas.sh"

ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
CANONICAL_ROOT="/mnt/cpool/compose/nabla-compose"
APP_ID="ntopng"
COMPOSE_PATH="${CANONICAL_ROOT}/apps/ntopng/compose.yml"
LICENSE_FILE="/mnt/cpool/ntopng/ntopng.license"
SECRET_FILE="/mnt/cpool/secrets/runtime/ntopng/.env.secrets"
DATA_ROOT="/mnt/cpool/ntopng"

[[ "${EUID}" -eq 0 ]] || fail "run via sudo on TrueNAS"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "canonical TrueNAS checkout required: ${CANONICAL_ROOT}"
for cmd in docker git jq midclt stat ip; do
  command -v "${cmd}" >/dev/null 2>&1 || fail "missing required command: ${cmd}"
done
truenas_repo_provenance "${ROOT}"
cd "${CANONICAL_ROOT}"

[[ -f "${COMPOSE_PATH}" && ! -L "${COMPOSE_PATH}" ]] ||
  fail "missing or symlinked Compose declaration"
[[ -d "${DATA_ROOT}" && ! -L "${DATA_ROOT}" ]] ||
  fail "missing or symlinked persistent ntopng dataset; provision and back up first"
[[ -d "${DATA_ROOT}/redis" && ! -L "${DATA_ROOT}/redis" ]] ||
  fail "missing persistent ntopng Redis directory"
for path in "${LICENSE_FILE}" "${SECRET_FILE}"; do
  [[ -f "${path}" && ! -L "${path}" && -s "${path}" ]] ||
    fail "missing, empty or symlinked required private file: ${path}"
  [[ "$(stat -c '%u:%g %a' "${path}")" == "0:0 600" ]] ||
    fail "private file must be root:root mode 0600: ${path}"
done
grep -Eq '^NTOPNG_CLICKHOUSE_PASSWORD=.+' "${SECRET_FILE}" ||
  fail "dedicated ClickHouse secret variable missing or empty"

# On host-network capture, a default interface must never be guessed.
[[ -n "${NTOPNG_INTERFACE:-}" && "${NTOPNG_INTERFACE}" != "lo" ]] ||
  fail "set NTOPNG_INTERFACE explicitly to an approved TrueNAS capture interface"
[[ "${NTOPNG_INTERFACE}" =~ ^[a-zA-Z0-9_.:-]+$ ]] ||
  fail "invalid capture interface name"
ip link show dev "${NTOPNG_INTERFACE}" >/dev/null 2>&1 ||
  fail "capture interface is not present on TrueNAS"

docker compose -f "${COMPOSE_PATH}" config \
  --quiet --no-interpolate --no-env-resolution

app_list="$(truenas_app_query_by_id "${APP_ID}")"
app_count="$(printf '%s' "${app_list}" | jq 'length')"
[[ "${app_count}" =~ ^[01]$ ]] ||
  fail "ntopng app identity ambiguous in TrueNAS middleware"

printf 'ntopng_mode=%s\n' "${MODE}"
printf 'ntopng_app_state=%s\n' "$(truenas_app_state "${APP_ID}")"
printf '%s\n' "ntopng_secret=private_present" "ntopng_license=private_present"
printf '%s\n' "ntopng_capture_interface=validated"
printf '%s\n' "ntopng_clickhouse_credential=present_not_authenticated"
printf '%s\n' "ntopng_license_edition=operator_validation_required"

if [[ "${MODE}" == "--check" ]]; then
  printf '%s\n' "ntopng_mutations=0" "ntopng_runtime_acceptance=NOT_VERIFIED"
  exit 0
fi

[[ "${NABLA_RUNTIME_CHANGE_APPROVED:-}" == "yes" ]] ||
  fail "set NABLA_RUNTIME_CHANGE_APPROVED=yes after a reviewed change plan"
[[ "${NABLA_NTOPNG_LICENSE_VALIDATED:-}" == "yes" ]] ||
  fail "independent validation of Enterprise M+ license is required"
[[ "${NABLA_NTOPNG_CLICKHOUSE_VALIDATED:-}" == "yes" ]] ||
  fail "independent, scoped ClickHouse credential and grants validation is required"
if [[ "${app_count}" == "1" ]]; then
  [[ "${NABLA_NTOPNG_UPDATE_APPROVED:-}" == "yes" ]] ||
    fail "existing app update requires separate NABLA_NTOPNG_UPDATE_APPROVED=yes"
fi

# TrueNAS middleware retains authority; never start the Compose project directly on an existing App.
truenas_reconcile_custom_app "${APP_ID}" "${COMPOSE_PATH}"
truenas_wait_app_running "${APP_ID}" 600 5
truenas_app_summary "${APP_ID}"
printf '%s\n' "ntopng_deployment=middleware_reconciled" \
  "ntopng_data_and_clickhouse_flow_acceptance=NOT_VERIFIED"
