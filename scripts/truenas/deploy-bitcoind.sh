#!/usr/bin/env bash
# Deploy the repository-managed bitcoind Custom App on TrueNAS.
#
#   sudo bash scripts/truenas/deploy-bitcoind.sh --check
#   sudo bash scripts/truenas/deploy-bitcoind.sh --apply
#   sudo NABLA_BITCOIND_REPLACE_APPROVED=yes \
#     bash scripts/truenas/deploy-bitcoind.sh --apply --replace-catalog-app
#
# --check (default) changes nothing. --apply prepares cpool/bitcoind and
# creates/updates the Custom App. A legacy TrueNAS catalog app with the same id
# is deleted (with its ix-volumes) only with --replace-catalog-app and
# NABLA_BITCOIND_REPLACE_APPROVED=yes: the blockchain is reproducible and the
# node has no wallet. Host-path datasets of the legacy app are only reported.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/truenas.sh
source "${SCRIPT_DIR}/../lib/truenas.sh"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

truenas_repo_provenance "$(git rev-parse --show-toplevel)"

MODE="${1:---check}"
REPLACE="${2:-}"
APP_ID="${BITCOIND_APP_ID:-bitcoind}"
CANONICAL_ROOT="${BITCOIND_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
DATASET="${BITCOIND_DATASET:-cpool/bitcoind}"
DATA_DIR="${BITCOIND_DATA_DIR:-/mnt/cpool/bitcoind/node}"
APPS_UID=568

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: sudo bash scripts/truenas/deploy-bitcoind.sh [--check|--apply] [--replace-catalog-app]" ;;
esac
case "${REPLACE}" in
  "" | --replace-catalog-app) ;;
  *) fail "unsupported option: ${REPLACE}" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run with sudo so TrueNAS middleware and ZFS can be managed"
for command in docker git jq midclt zfs; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done
ROOT="$(git rev-parse --show-toplevel)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical TrueNAS checkout ${CANONICAL_ROOT}; current checkout is ${ROOT}"
cd "${CANONICAL_ROOT}"

compose_path="${CANONICAL_ROOT}/apps/bitcoind/compose.yml"
[[ -f "${compose_path}" ]] || fail "missing ${compose_path}"
docker compose -f "${compose_path}" config --quiet --no-interpolate --no-env-resolution

section "Current state"
app_json="$(truenas_app_query_by_id "${APP_ID}")"
app_kind="$(jq -r 'if length == 0 then "missing" elif .[0].custom_app then "custom" else "catalog" end' <<<"${app_json}")"
printf 'app %s: %s (state=%s)\n' "${APP_ID}" "${app_kind}" "$(jq -r '.[0].state // "MISSING"' <<<"${app_json}")"
printf 'bitcoin-related datasets (name used usedbysnapshots snapshots):\n'
while IFS=$'\t' read -r name used snapused; do
  [[ -n "${name}" ]] || continue
  printf '  %s %s %s %s\n' "${name}" "${used}" "${snapused}" \
    "$(zfs list -H -t snapshot -o name -d 1 "${name}" 2>/dev/null | wc -l)"
done < <(zfs list -H -o name,used,usedbysnapshots | grep -i bitcoin || true)
if [[ -d "${DATA_DIR}" ]]; then
  printf 'data dir %s owner=%s mode=%s\n' "${DATA_DIR}" "$(stat -c '%u:%g' "${DATA_DIR}")" "$(stat -c '%a' "${DATA_DIR}")"
else
  printf 'data dir %s: absent (created by --apply)\n' "${DATA_DIR}"
fi

if [[ "${MODE}" == "--check" ]]; then
  if [[ "${app_kind}" == "catalog" ]]; then
    warn "legacy catalog app ${APP_ID} present: replace it with NABLA_BITCOIND_REPLACE_APPROVED=yes ... --apply --replace-catalog-app"
  fi
  ok "check complete; nothing changed"
  exit 0
fi

section "Apply"
if [[ "${app_kind}" == "catalog" ]]; then
  [[ "${REPLACE}" == "--replace-catalog-app" && "${NABLA_BITCOIND_REPLACE_APPROVED:-}" == "yes" ]] ||
    fail "legacy catalog app ${APP_ID} present: --replace-catalog-app and NABLA_BITCOIND_REPLACE_APPROVED=yes are required"
  printf 'Deleting legacy catalog app %s with its ix-volumes and images...\n' "${APP_ID}"
  truenas_job_compact app.delete "${APP_ID}" '{"remove_images": true, "remove_ix_volumes": true}'
fi

bash scripts/truenas/bootstrap-repository-runtime.sh --apply "${APP_ID}"
zfs list -H -o name "${DATASET}" >/dev/null 2>&1 || fail "dataset ${DATASET} missing after storage bootstrap"
install -d -o "${APPS_UID}" -g "${APPS_UID}" -m 0750 "${DATA_DIR}"

truenas_reconcile_custom_app "${APP_ID}" "${compose_path}"
truenas_app_summary "${APP_ID}"
printf 'Initial block download runs for hours; health turns healthy once RPC answers.\n'
printf 'Follow: sudo docker logs --tail 50 -f bitcoind\n'
