#!/usr/bin/env bash
# Controlled TrueNAS ntopng Community Custom App deployment. No auto-creation of datasets.
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
CONFIG_PATH="${CANONICAL_ROOT}/apps/ntopng/ntopng.conf"
DATA_ROOT="/mnt/cpool/ntopng"

[[ "${EUID}" -eq 0 ]] || fail "run via sudo on TrueNAS"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "canonical TrueNAS checkout required: ${CANONICAL_ROOT}"
for cmd in docker git jq midclt sed ip; do
  command -v "${cmd}" >/dev/null 2>&1 || fail "missing required command: ${cmd}"
done
truenas_repo_provenance "${ROOT}"
cd "${CANONICAL_ROOT}"

for path in "${COMPOSE_PATH}" "${CONFIG_PATH}"; do
  [[ -f "${path}" && ! -L "${path}" ]] || fail "missing or symlinked declaration: ${path}"
done
[[ -d "${DATA_ROOT}" && ! -L "${DATA_ROOT}" ]] ||
  fail "missing or symlinked persistent ntopng dataset; run bootstrap-repository-storage.sh --apply ntopng"

# The capture interface is reviewed in Git (ntopng.conf); it must exist and never be lo.
interface="$(sed -n 's/^--interface=//p' "${CONFIG_PATH}")"
[[ "${interface}" =~ ^[a-zA-Z0-9_.:-]+$ && "${interface}" != "lo" ]] ||
  fail "ntopng.conf needs exactly one reviewed --interface"
ip link show dev "${interface}" >/dev/null 2>&1 ||
  fail "capture interface ${interface} is not present on TrueNAS"

docker compose -f "${COMPOSE_PATH}" config \
  --quiet --no-interpolate --no-env-resolution

app_list="$(truenas_app_query_by_id "${APP_ID}")"
app_count="$(printf '%s' "${app_list}" | jq 'length')"
[[ "${app_count}" =~ ^[01]$ ]] ||
  fail "ntopng app identity ambiguous in TrueNAS middleware"

printf 'ntopng_mode=%s\n' "${MODE}"
printf 'ntopng_app_state=%s\n' "$(truenas_app_state "${APP_ID}")"
printf 'ntopng_capture_interface=%s\n' "${interface}"
printf '%s\n' "ntopng_edition=community"

if [[ "${MODE}" == "--check" ]]; then
  printf '%s\n' "ntopng_mutations=0" "ntopng_runtime_acceptance=NOT_VERIFIED"
  exit 0
fi

[[ "${NABLA_RUNTIME_CHANGE_APPROVED:-}" == "yes" ]] ||
  fail "set NABLA_RUNTIME_CHANGE_APPROVED=yes after a reviewed change plan"
if [[ "${app_count}" == "1" ]]; then
  [[ "${NABLA_NTOPNG_UPDATE_APPROVED:-}" == "yes" ]] ||
    fail "existing app update requires separate NABLA_NTOPNG_UPDATE_APPROVED=yes"
fi

# TrueNAS middleware retains authority; never start the Compose project directly on an existing App.
truenas_reconcile_custom_app "${APP_ID}" "${COMPOSE_PATH}"
truenas_wait_app_running "${APP_ID}" 600 5
truenas_app_summary "${APP_ID}"
printf '%s\n' "ntopng_deployment=middleware_reconciled" \
  "ntopng_next=change the default admin/admin password at first login, store it in nabla/prod/ntopng"
