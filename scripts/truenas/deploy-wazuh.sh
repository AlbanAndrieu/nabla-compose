#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/truenas.sh
source "${SCRIPT_DIR}/../lib/truenas.sh"

APP_ID="${WAZUH_APP_ID:-wazuh}"
WAIT_ATTEMPTS="${WAZUH_WAIT_ATTEMPTS:-240}"
WAIT_DELAY="${WAZUH_WAIT_DELAY_SECONDS:-5}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] ||
  fail "run with sudo so bootstrap files stay root-owned"

for command in docker git jq midclt curl; do
  command -v "${command}" >/dev/null 2>&1 ||
    fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
CANONICAL_ROOT="${WAZUH_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
cd "${ROOT}"

if [[ "${ROOT}" != "${CANONICAL_ROOT}" ]]; then
  printf 'NOTE: Wazuh compose include will be persisted from non-canonical checkout: %s\n' "${ROOT}"
  printf '      after merge, rerun this deploy from %s to remove worktree drift.\n' "${CANONICAL_ROOT}"
fi

bash scripts/truenas/bootstrap-wazuh.sh --apply
bash scripts/truenas/bootstrap-wazuh.sh --check

docker compose \
  -f apps/wazuh/compose.yml \
  config \
  --quiet \
  --no-interpolate \
  --no-env-resolution

compose_path="${ROOT}/apps/wazuh/compose.yml"

if truenas_app_query_by_id "${APP_ID}" |
  jq -e 'length > 0' >/dev/null; then
  printf 'Updating existing TrueNAS Custom App %s...\n' "${APP_ID}"
  truenas_job_compact app.update "${APP_ID}" "$(
    jq -cn --arg include "${compose_path}" '{
      custom_compose_config: {
        include: [$include]
      }
    }'
  )"
else
  printf 'Creating missing TrueNAS Custom App %s...\n' "${APP_ID}"
  wrapper="$(printf 'include:\n  - %s\n' "${compose_path}")"
  truenas_job_compact app.create "$(
    jq -cn \
      --arg app_name "${APP_ID}" \
      --arg compose "${wrapper}" \
      '{
        app_name: $app_name,
        custom_app: true,
        custom_compose_config_string: $compose
      }'
  )"
fi

app_state="$(
  truenas_app_query_by_id "${APP_ID}" |
    jq -r '.[0].state // "MISSING"'
)"
case "${app_state}" in
  STOPPED)
    printf 'Starting TrueNAS Custom App %s after configuration reconciliation...\n' "${APP_ID}"
    truenas_job_compact app.start "${APP_ID}"
    ;;
  RUNNING | DEPLOYING)
    printf 'TrueNAS Custom App %s is already %s; continuing convergence checks.\n'       "${APP_ID}" "${app_state}"
    ;;
  CRASHED)
    printf 'TrueNAS Custom App %s is CRASHED after reconciliation; attempting one controlled start.\n' "${APP_ID}"
    truenas_job_compact app.start "${APP_ID}"
    ;;
  *)
    fail "unexpected TrueNAS App state after reconciliation: ${app_state}"
    ;;
esac

if docker network inspect nabla-security >/dev/null 2>&1; then
  printf 'Optional Wazuh forwarding network nabla-security is present.\n'
else
  printf 'NOTE: nabla-security is absent; Wazuh core is unaffected because forwarding is profile-gated.\n'
fi

last_diagnostic=""
for ((attempt = 1; attempt <= WAIT_ATTEMPTS; attempt++)); do
  if last_diagnostic="$(
    bash scripts/truenas/diagnose-wazuh.sh --check 2>&1
  )"; then
    printf '%s\n' "${last_diagnostic}"
    exit 0
  fi

  if ((attempt == 1 || attempt % 10 == 0)); then
    state="$(
      truenas_app_query_by_id "${APP_ID}" |
        jq -r '.[0].state // "UNKNOWN"'
    )"
    printf 'Wazuh not converged yet (%d/%d, TrueNAS=%s; first startup may initialize persistent volumes/indexes)\n' \
      "${attempt}" "${WAIT_ATTEMPTS}" "${state}"
  fi
  sleep "${WAIT_DELAY}"
done

printf '%s\n' "${last_diagnostic}" >&2
truenas_app_query_by_id "${APP_ID}" |
  jq '.[0] | {id,state,active_workloads}' >&2 || true

docker ps -a \
  --filter 'label=com.docker.compose.project=ix-wazuh' \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' >&2 || true

for container in wazuh-indexer wazuh-manager wazuh-dashboard; do
  printf '\n=== %s last logs ===\n' "${container}" >&2
  docker logs --tail 80 "${container}" >&2 2>/dev/null || true
done

fail "Wazuh did not converge within the configured wait window"
