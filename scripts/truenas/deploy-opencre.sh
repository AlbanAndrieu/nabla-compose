#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
APP_ID="${OPENCRE_APP_ID:-opencre}"
CANONICAL_ROOT="${OPENCRE_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
OPENCRE_URL="${OPENCRE_URL:-http://172.17.0.24:31089/rest/v1/health}"
OPENCRE_IMAGE="${OPENCRE_IMAGE:-ghcr.io/owasp/opencre/opencre:latest}"
WAIT_SECONDS="${OPENCRE_WAIT_SECONDS:-600}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: sudo bash $0 [--check|--apply]" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run with sudo on TrueNAS"
for command in curl docker git jq midclt python3; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical checkout ${CANONICAL_ROOT}; current=${ROOT}"
cd "${CANONICAL_ROOT}"

source "${CANONICAL_ROOT}/scripts/lib/truenas.sh"

compose_path="${CANONICAL_ROOT}/apps/opencre/compose.yml"
[[ -f "${compose_path}" ]] || fail "missing ${compose_path}"

printf '==> OpenCRE image contract\n'
if [[ "${OPENCRE_IMAGE}" == *@sha256:* ]]; then
  printf 'OK: immutable OpenCRE image reference selected\n'
else
  printf 'WARNING: OpenCRE image is mutable: %s\n' "${OPENCRE_IMAGE}" >&2
  if [[ "${MODE}" == "--apply" && "${OPENCRE_ALLOW_MUTABLE_IMAGE:-0}" != "1" ]]; then
    fail \
      "refusing OpenCRE --apply with mutable image; use an @sha256 digest or " \
      "OPENCRE_ALLOW_MUTABLE_IMAGE=1 for a bounded PoC"
  fi
fi

printf '\n==> OpenCRE Compose contract\n'
OPENCRE_IMAGE="${OPENCRE_IMAGE}" \
  docker compose -f "${compose_path}" config \
  --quiet --no-interpolate --no-env-resolution

printf '\n==> generated service contracts\n'
python3 scripts/generate-service-topology.py --check
python3 scripts/generate-service-consumers.py --check

printf '\n==> OpenCRE repository-owned storage\n'
bash scripts/truenas/bootstrap-repository-storage.sh "${MODE}" "${APP_ID}"

if [[ "${MODE}" == "--apply" ]]; then
  printf '\n==> TrueNAS Custom App reconciliation\n'
  OPENCRE_IMAGE="${OPENCRE_IMAGE}" \
    truenas_reconcile_custom_app "${APP_ID}" "${compose_path}"
fi

state="$(truenas_app_state "${APP_ID}")"
[[ "${state}" != "MISSING" ]] ||
  fail "${APP_ID}: TrueNAS Custom App is not registered; run --apply"

printf '\n==> wait for OpenCRE runtime\n'
truenas_wait_app_running "${APP_ID}" "${WAIT_SECONDS}" 5

deadline=$((SECONDS + WAIT_SECONDS))
while ((SECONDS < deadline)); do
  if curl -fsS --connect-timeout 3 --max-time 8 -o /dev/null "${OPENCRE_URL}"; then
    printf 'OK: OpenCRE health endpoint ready: %s\n' "${OPENCRE_URL}"
    printf '%s%s\n' \
      'INFO: x-nabla.status remains planned until immutable-image, correlation, ' \
      'persistence and reboot acceptance are reviewed.'
    exit 0
  fi
  sleep 5
done

fail "OpenCRE health endpoint did not become ready within ${WAIT_SECONDS}s: ${OPENCRE_URL}"
