#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
TARGET="${2:-all}"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
CANONICAL_ROOT="${NABLA_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
PERSISTENT_APPS=(plumber netbox dependency-track defectdojo neo4j)
MANUAL_APPS=(cartography scorecard)

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}
note() {
  printf '==> %s\n' "$*"
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: sudo -E bash $0 [--check|--apply] [app|all]" ;;
esac
[[ "${EUID}" -eq 0 ]] || fail "run with sudo -E"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical checkout ${CANONICAL_ROOT}; current=${ROOT}"
for command in curl docker jq midclt python3; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

# shellcheck source=../lib/truenas.sh
source "${ROOT}/scripts/lib/truenas.sh"

all_apps=("${PERSISTENT_APPS[@]}" "${MANUAL_APPS[@]}")
if [[ "${TARGET}" != "all" ]]; then
  found=0
  for app in "${all_apps[@]}"; do
    [[ "${app}" == "${TARGET}" ]] && found=1
  done
  ((found == 1)) || fail "unsupported app: ${TARGET}"
  all_apps=("${TARGET}")
fi

is_persistent() {
  local target="$1" app
  for app in "${PERSISTENT_APPS[@]}"; do
    [[ "${target}" == "${app}" ]] && return 0
  done
  return 1
}

postgres_app() {
  case "$1" in
    plumber | netbox | dependency-track | defectdojo) return 0 ;;
    *) return 1 ;;
  esac
}

app_url() {
  case "$1" in
    plumber) printf '%s\n' 'http://172.17.0.24:31070/' ;;
    netbox) printf '%s\n' 'http://172.17.0.24:31082/' ;;
    dependency-track) printf '%s\n' 'http://172.17.0.24:31084/' ;;
    defectdojo) printf '%s\n' 'http://172.17.0.24:31085/' ;;
    neo4j) printf '%s\n' 'http://172.17.0.24:31086/' ;;
    *) return 1 ;;
  esac
}

wait_http() {
  local app="$1" url="$2" timeout_seconds=300
  case "${app}" in
    netbox | dependency-track | defectdojo) timeout_seconds=600 ;;
  esac
  local deadline=$((SECONDS + timeout_seconds))
  while ((SECONDS < deadline)); do
    if curl -fsS --connect-timeout 5 --max-time 10 -o /dev/null "${url}"; then
      printf 'OK: %s HTTP ready: %s\n' "${app}" "${url}"
      return 0
    fi
    sleep 5
  done
  fail "${app}: HTTP endpoint did not become ready within ${timeout_seconds}s: ${url}"
}

note "validate generated topology/catalog contracts"
python3 scripts/generate-service-topology.py --check
python3 scripts/generate-service-consumers.py --check
python3 scripts/secrets/render_from_bitwarden.py --check

for app in "${all_apps[@]}"; do
  note "${app}: secret materialization"
  bash scripts/truenas/prepare-security-tooling-secrets.sh --check "${app}"
  if [[ "${NABLA_VERIFY_VAULTWARDEN:-0}" == "1" ]]; then
    bash scripts/truenas/prepare-security-tooling-secrets.sh --verify-vaultwarden "${app}"
  fi

  compose_path="${ROOT}/apps/${app}/compose.yml"
  [[ -f "${compose_path}" ]] || fail "${app}: missing ${compose_path}"

  note "${app}: Compose validation"
  if is_persistent "${app}"; then
    docker compose -f "${compose_path}" config --quiet --no-interpolate --no-env-resolution
  else
    docker compose -f "${compose_path}" --profile manual config --quiet --no-interpolate --no-env-resolution
    printf 'OK: %s is a manual job; not registered as an always-on TrueNAS App\n' "${app}"
    continue
  fi

  if [[ "${MODE}" == "--apply" ]]; then
    note "${app}: storage reconciliation"
    bash scripts/truenas/bootstrap-repository-storage.sh --apply "${app}"
  fi
  bash scripts/truenas/bootstrap-repository-storage.sh --check "${app}"

  if postgres_app "${app}"; then
    note "${app}: shared PostgreSQL"
    bash scripts/truenas/bootstrap-security-tooling-postgres.sh "${MODE}" "${app}"
  fi

  if [[ "${MODE}" == "--apply" ]]; then
    note "${app}: TrueNAS Custom App reconciliation"
    truenas_reconcile_custom_app "${app}" "${compose_path}"
  else
    [[ "$(truenas_app_state "${app}")" != "MISSING" ]] ||
      fail "${app}: TrueNAS Custom App is not registered"
  fi

  note "${app}: middleware/container stability"
  truenas_wait_app_running "${app}" 600 5
  NABLA_APP_HEALTH_TIMEOUT_SECONDS=600     bash scripts/truenas/verify-app-runtime-health.sh "${app}"

  url="$(app_url "${app}")"
  wait_http "${app}" "${url}"
done

printf 'OK: security tooling %s completed target=%s\n' "${MODE}" "${TARGET}"
