#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"
# shellcheck source=../lib/secrets.sh
source "${SCRIPT_DIR}/../lib/secrets.sh"

MODE="${1:---check}"
APP_FILTER="${2:-all}"
CANONICAL_ROOT="${NABLA_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
RUNTIME_ROOT="${NABLA_RUNTIME_ENV_ROOT:-/mnt/cpool/secrets/runtime}"
HEALTH_SCRIPT="${SCRIPT_DIR}/verify-app-runtime-health.sh"

SERVICES=(scanopy joplin autokuma)

function usage {
  cat <<'EOF'
usage:
  sudo bash scripts/truenas/accept-runtime-env-first-wave.sh --check [scanopy|joplin|autokuma|all]
  sudo bash scripts/truenas/accept-runtime-env-first-wave.sh --stage [scanopy|joplin|autokuma|all]
  sudo bash scripts/truenas/accept-runtime-env-first-wave.sh --accept <scanopy|joplin|autokuma>

--check   read-only canonical runtime/env contract check
--stage   create/stage canonical runtime materialization; keep legacy sources intact
--accept  stage one service, reconcile dependencies/runtime, verify health, then finalize
EOF
}

case "${MODE}" in
  --check | --stage | --accept) ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

case "${APP_FILTER}" in
  scanopy | joplin | autokuma | all) ;;
  *)
    fail "unsupported first-wave service: ${APP_FILTER}"
    ;;
esac
if [[ "${MODE}" == "--accept" && "${APP_FILTER}" == "all" ]]; then
  fail "--accept is deliberately one service at a time"
fi

require_root "run as root on TrueNAS"
require_commands bash curl git grep jq midclt stat
[[ -x "${HEALTH_SCRIPT}" ]] || fail "missing runtime health helper: ${HEALTH_SCRIPT}"

ROOT="$(git rev-parse --show-toplevel)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical TrueNAS checkout ${CANONICAL_ROOT}; current checkout is ${ROOT}"
cd "${CANONICAL_ROOT}"

function selected_services {
  local app
  if [[ "${APP_FILTER}" == "all" ]]; then
    printf '%s\n' "${SERVICES[@]}"
    return 0
  fi
  for app in "${SERVICES[@]}"; do
    [[ "${app}" == "${APP_FILTER}" ]] && printf '%s\n' "${app}"
  done
}

function secret_file {
  printf '%s/%s/.env.secrets\n' "${RUNTIME_ROOT}" "$1"
}

function check_secret_contract {
  local app="$1" file
  file="$(secret_file "${app}")"
  case "${app}" in
    scanopy)
      secrets_assert_file "${file}" POSTGRES_PASSWORD SCANOPY_DATABASE_URL
      ;;
    joplin)
      secrets_assert_file "${file}" POSTGRES_PASSWORD
      ;;
    autokuma)
      secrets_assert_file "${file}" AUTOKUMA__KUMA__AUTH_TOKEN
      ;;
  esac
}

function check_vaultwarden_materialization {
  local app="$1" file
  file="$(secret_file "${app}")"
  if ! grep -Fq -- \
    '# Generated from Vaultwarden by scripts/secrets/render_from_bitwarden.py' \
    "${file}"; then
    fail "${app}: canonical runtime secret is not a Vaultwarden materialization; run as the unlocked operator: python scripts/secrets/materialize_runtime.py --app ${app} --install"
  fi
}

function check_compose_contract {
  local app="$1" compose="${CANONICAL_ROOT}/apps/$1/compose.yml"
  local expected="${RUNTIME_ROOT}/$1/.env.secrets"
  [[ -f "${compose}" ]] || fail "missing Compose file: ${compose}"
  grep -Fq -- "${expected}" "${compose}" ||
    fail "${app}: Compose does not reference canonical runtime secret file ${expected}"
}

function check_service {
  local app="$1"
  printf '\n== P0.3 check: %s ==\n' "${app}"
  bash scripts/truenas/bootstrap-repository-runtime.sh --check "${app}"
  check_compose_contract "${app}"
  check_secret_contract "${app}"
  ok "${app}: canonical runtime/env contract is ready"
}

function stage_service {
  local app="$1"
  printf '\n== P0.3 stage: %s ==\n' "${app}"
  bash scripts/truenas/bootstrap-repository-runtime.sh --apply "${app}"
  check_service "${app}"
}

function accept_dependency {
  local app="$1"
  case "${app}" in
    scanopy)
      bash scripts/truenas/bootstrap-scanopy-postgres.sh --apply
      ;;
    joplin)
      bash scripts/truenas/bootstrap-joplin-postgres.sh --apply
      ;;
    autokuma)
      if ! midclt call app.query '[["id","=","uptime-kuma"]]' |
        jq -e '[.[] | select(.id == "uptime-kuma" and .state == "RUNNING")] | length == 1' >/dev/null; then
        fail "autokuma: Uptime Kuma must exist and be RUNNING before acceptance"
      fi
      curl --fail --silent --show-error --max-time 10 \
        http://172.17.0.24:31050/ >/dev/null ||
        fail "autokuma: Uptime Kuma API/UI is not reachable on 172.17.0.24:31050"
      ;;
  esac
}

function deploy_service {
  local app="$1"
  case "${app}" in
    scanopy) bash scripts/truenas/deploy-scanopy.sh ;;
    joplin) bash scripts/truenas/deploy-joplin.sh ;;
    autokuma) bash scripts/truenas/deploy-autokuma.sh ;;
  esac
  bash "${HEALTH_SCRIPT}" "${app}"
}

function functional_probe {
  local app="$1"
  case "${app}" in
    scanopy)
      curl --fail --silent --show-error --max-time 10 \
        http://172.17.0.24:60072/ >/dev/null
      ;;
    joplin)
      curl --fail --silent --show-error --max-time 10 \
        http://172.17.0.24:22300/api/ping >/dev/null
      ;;
    autokuma)
      # AutoKuma is a controller without an HTTP surface of its own. Runtime
      # stability plus the explicit Uptime Kuma dependency probe is its gate.
      return 0
      ;;
  esac
}

function accept_service {
  local app="$1"
  stage_service "${app}"
  check_vaultwarden_materialization "${app}"
  accept_dependency "${app}"
  deploy_service "${app}"
  functional_probe "${app}" ||
    fail "${app}: functional acceptance probe failed"

  bash scripts/truenas/bootstrap-repository-env-files.sh --finalize "${app}"
  bash scripts/truenas/bootstrap-repository-runtime.sh --check "${app}"
  ok "${app}: P0.3 runtime/env migration accepted and legacy path finalized"
}

while IFS= read -r app; do
  [[ -n "${app}" ]] || continue
  case "${MODE}" in
    --check) check_service "${app}" ;;
    --stage) stage_service "${app}" ;;
    --accept) accept_service "${app}" ;;
  esac
done < <(selected_services)
