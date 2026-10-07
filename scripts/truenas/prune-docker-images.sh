#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
MIN_AGE_HOURS="${NABLA_DOCKER_IMAGE_PRUNE_MIN_AGE_HOURS:-168}"
REBOOT_STATE_ROOT="${NABLA_REBOOT_STATE_ROOT:-/mnt/cpool/var/nabla/reboot}"
LOCK_FILE="${NABLA_DOCKER_IMAGE_PRUNE_LOCK_FILE:-/tmp/nabla-docker-image-prune.lock}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
AUDIT="${NABLA_DOCKER_STORAGE_AUDIT:-${SCRIPT_DIR}/audit-docker-storage-debt.sh}"
# shellcheck source=../lib/truenas.sh
source "${SCRIPT_DIR}/../lib/truenas.sh"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}
skip() {
  printf 'SKIP: %s\n' "$*"
  exit 0
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: sudo bash scripts/truenas/prune-docker-images.sh [--check|--apply]" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run as root on TrueNAS"
[[ "${MIN_AGE_HOURS}" =~ ^[1-9][0-9]*$ ]] ||
  fail "NABLA_DOCKER_IMAGE_PRUNE_MIN_AGE_HOURS must be a positive integer"
for command in docker flock midclt jq systemctl; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done
[[ -x "${AUDIT}" || -f "${AUDIT}" ]] || fail "storage audit helper missing: ${AUDIT}"

exec 9>"${LOCK_FILE}"
flock -n 9 || skip "another Docker image-maintenance job is already running"

if [[ -f "${REBOOT_STATE_ROOT}/latest" ]]; then
  state_dir="$(cat "${REBOOT_STATE_ROOT}/latest" 2>/dev/null || true)"
  phase=""
  [[ -n "${state_dir}" && -f "${state_dir}/phase" ]] &&
    phase="$(cat "${state_dir}/phase" 2>/dev/null || true)"
  case "${phase}" in
    PREPARING | PREPARED | RESUMED)
      skip "reboot transaction is active (phase=${phase}); Docker cleanup is forbidden until VERIFIED"
      ;;
  esac
fi

service_state="$(systemctl is-active docker 2>/dev/null || true)"
middleware_state="$(truenas_docker_status || true)"
[[ "${service_state}" == "active" && "${middleware_state}" == "RUNNING" ]] ||
  skip "Docker is not fully converged (service=${service_state:-unknown} middleware=${middleware_state:-UNKNOWN})"

printf 'Docker dangling-image maintenance mode=%s min_age=%sh\n' "${MODE}" "${MIN_AGE_HOURS}"
printf '%s\n' \
  'Policy: dangling images only; never --all/-a; networks, volumes and containers are untouched.' \
  'Recent dangling images are retained as a short rollback/debug window.'

bash "${AUDIT}" --check

printf '\nDangling images currently visible:\n'
docker image ls --filter dangling=true \
  --format 'table {{.ID}}\t{{.Repository}}\t{{.Tag}}\t{{.CreatedSince}}\t{{.Size}}'

[[ "${MODE}" == "--apply" ]] || {
  printf 'READ-ONLY: use --apply to prune dangling images older than %sh.\n' "${MIN_AGE_HOURS}"
  exit 0
}

printf '\nApplying bounded dangling-image prune (until=%sh)...\n' "${MIN_AGE_HOURS}"
docker image prune -f --filter "until=${MIN_AGE_HOURS}h"

printf '\nPost-cleanup audit:\n'
bash "${AUDIT}" --check
