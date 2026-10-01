set -euo pipefail

MODE="${1:---check}"
APP_ID="${DSOMM_APP_ID:-dsomm}"
CANONICAL_ROOT="${DSOMM_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
DSOMM_URL="${DSOMM_URL:-http://172.17.0.24:31088/}"
WAIT_SECONDS="${DSOMM_WAIT_SECONDS:-240}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: sudo bash $0 [--check|--apply]" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run with sudo on TrueNAS"
for command in curl docker git install jq midclt python3; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical checkout ${CANONICAL_ROOT}; current=${ROOT}"
cd "${CANONICAL_ROOT}"

# shellcheck source=../lib/truenas.sh
source "${CANONICAL_ROOT}/scripts/lib/truenas.sh"

compose_path="${CANONICAL_ROOT}/apps/dsomm/compose.yml"
[[ -f "${compose_path}" ]] || fail "missing ${compose_path}"

printf '==> DSOMM repository-owned storage\n'
bash scripts/truenas/bootstrap-repository-storage.sh "${MODE}" "${APP_ID}"

state_root="/mnt/cpool/dsomm/state"
progress_file="${state_root}/team-progress.yaml"
evidence_file="${state_root}/team-evidence.yaml"

if [[ "${MODE}" == "--apply" ]]; then
  install -d -m 0700 "${state_root}"
  umask 077
  if [[ ! -e "${progress_file}" ]]; then
    printf 'progress:\n' >"${progress_file}"
  fi
  if [[ ! -e "${evidence_file}" ]]; then
    printf 'evidence:\n' >"${evidence_file}"
  fi
  chmod 0600 "${progress_file}" "${evidence_file}"
fi

for state_file in "${progress_file}" "${evidence_file}"; do
  [[ -f "${state_file}" && ! -L "${state_file}" ]] ||
    fail "missing or unsafe DSOMM state file: ${state_file}; run --apply"
done

printf '==> DSOMM Compose contract\n'
docker compose -f "${compose_path}" --profile manual config   --quiet --no-interpolate --no-env-resolution

printf '\n==> generated service contracts\n'
python3 scripts/generate-service-topology.py --check
python3 scripts/generate-service-consumers.py --check

if [[ "${MODE}" == "--apply" ]]; then
  printf '\n==> TrueNAS Custom App reconciliation\n'
  truenas_reconcile_custom_app "${APP_ID}" "${compose_path}"
fi

state="$(truenas_app_state "${APP_ID}")"
[[ "${state}" != "MISSING" ]] ||
  fail "${APP_ID}: TrueNAS Custom App is not registered; run --apply"

printf '\n==> wait for DSOMM runtime\n'
truenas_wait_app_running "${APP_ID}" "${WAIT_SECONDS}" 4

deadline=$((SECONDS + WAIT_SECONDS))
while ((SECONDS < deadline)); do
  if curl -fsS --connect-timeout 3 --max-time 8 -o /dev/null "${DSOMM_URL}"; then
    printf 'OK: DSOMM HTTP ready: %s\n' "${DSOMM_URL}"
    printf 'INFO: x-nabla.status remains planned until this runtime acceptance is reviewed and committed as active.\n'
    exit 0
  fi
  sleep 4
done

fail "DSOMM HTTP endpoint did not become ready within ${WAIT_SECONDS}s: ${DSOMM_URL}"
