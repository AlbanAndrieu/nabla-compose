#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

MODE="${1:---check}"
shift || true

APP_QUERY_TIMEOUT="${NABLA_STUCK_APP_QUERY_TIMEOUT_SECONDS:-90}"
LOG_TAIL="${NABLA_STUCK_APP_LOG_TAIL:-40}"
APP_FILTERS=()

usage() {
  cat <<'EOF'
usage:
  sudo bash scripts/truenas/diagnose-stuck-apps.sh --check [--app APP ...]

Read-only post-reboot diagnostic for TrueNAS Apps that are CRASHED, DEPLOYING
or STOPPED. It correlates:
- app.query lifecycle state
- recent app lifecycle jobs
- Docker Compose project containers
- health/restart/exit state
- bounded recent logs for unhealthy/restarting/non-zero-exit containers

With --app, only the named Apps are inspected.
EOF
}

case "${MODE}" in
  --check) ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    fail "unknown mode: ${MODE}"
    ;;
esac

while (($#)); do
  case "$1" in
    --app)
      (($# >= 2)) || fail "--app requires an App id"
      APP_FILTERS+=("$2")
      shift 2
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

require_root "run as root on TrueNAS"
require_commands timeout midclt jq docker grep tail sed head sort mktemp

for value in APP_QUERY_TIMEOUT LOG_TAIL; do
  current="${!value}"
  [[ "${current}" =~ ^[1-9][0-9]*$ ]] || fail "${value} must be a positive integer"
done

tmp="$(mktemp -d /tmp/nabla-stuck-apps.XXXXXX)"
trap 'rm -rf "${tmp}"' EXIT
apps_json="${tmp}/apps.json"
jobs_json="${tmp}/jobs.json"

timeout "${APP_QUERY_TIMEOUT}" midclt call app.query >"${apps_json}" ||
  fail "app.query did not respond within ${APP_QUERY_TIMEOUT}s"
timeout "${APP_QUERY_TIMEOUT}" midclt call core.get_jobs >"${jobs_json}" ||
  fail "core.get_jobs did not respond within ${APP_QUERY_TIMEOUT}s"

if (("${#APP_FILTERS[@]}" > 0)); then
  printf '%s\n' "${APP_FILTERS[@]}" >"${tmp}/selected.txt"
else
  jq -r '.[] | select(.state == "CRASHED" or .state == "DEPLOYING" or .state == "STOPPED") | .id'     "${apps_json}" | sort -u >"${tmp}/selected.txt"
fi

if [[ ! -s "${tmp}/selected.txt" ]]; then
  ok "no CRASHED/DEPLOYING/STOPPED Apps"
  exit 0
fi

failures=0
while IFS= read -r app; do
  [[ -n "${app}" ]] || continue
  app_state="$(
    jq -r --arg app "${app}" '.[] | select(.id == $app) | .state // "MISSING"' "${apps_json}" |
      head -n 1
  )"
  [[ -n "${app_state}" ]] || app_state="MISSING"

  printf '\n=== APP %s state=%s ===\n' "${app}" "${app_state}"

  printf '%s\n' '-- recent lifecycle jobs --'
  jq -r --arg app "${app}" '
    [
      .[]
      | select((.method // "") | startswith("app."))
      | select(((.arguments // []) | tostring) | contains($app))
      | {
          id,
          method,
          state,
          percent: (.progress.percent // null),
          description: (.progress.description // null),
          error
        }
    ]
    | sort_by(.id)
    | reverse
    | .[:5]
    | .[]
    | "job=\(.id) method=\(.method) state=\(.state) percent=\(.percent // "-") error=\(.error // "")"
  ' "${jobs_json}" || true

  project="ix-${app}"
  mapfile -t ids < <(
    docker ps -a --filter "label=com.docker.compose.project=${project}" --format '{{.ID}}'
  )

  if (("${#ids[@]}" == 0)); then
    printf 'containers=<none> project=%s\n' "${project}"
  fi

  for id in "${ids[@]}"; do
    inspect="$(docker inspect "${id}")"
    name="$(jq -r '.[0].Name | ltrimstr("/")' <<<"${inspect}")"
    service="$(jq -r '.[0].Config.Labels["com.docker.compose.service"] // "unknown"' <<<"${inspect}")"
    status="$(jq -r '.[0].State.Status // "unknown"' <<<"${inspect}")"
    health="$(jq -r '.[0].State.Health.Status // "none"' <<<"${inspect}")"
    exit_code="$(jq -r '.[0].State.ExitCode // 0' <<<"${inspect}")"
    restarts="$(jq -r '.[0].RestartCount // 0' <<<"${inspect}")"

    printf 'container=%s service=%s status=%s health=%s exit=%s restarts=%s\n'       "${name}" "${service}" "${status}" "${health}" "${exit_code}" "${restarts}"

    if [[ "${status}" == "restarting" || "${health}" == "unhealthy" || "${exit_code}" -ne 0 ]]; then
      printf '%s\n' '  recent logs:'
      docker logs --tail "${LOG_TAIL}" "${id}" 2>&1 |
        tail -n "${LOG_TAIL}" |
        sed 's/^/    /' || true
    fi
  done

  case "${app}" in
    sentry)
      printf 'NEXT: sudo bash scripts/truenas/diagnose-sentry.sh --check\n'
      ;;
    wazuh)
      printf 'NEXT: sudo bash scripts/truenas/diagnose-wazuh.sh --check\n'
      printf '      If prerequisites are valid and state stays STOPPED: sudo bash scripts/truenas/deploy-wazuh.sh\n'
      ;;
    langflow)
      printf 'NEXT: inspect the restart-loop logs above before changing image/configuration.\n'
      ;;
    i2p)
      printf 'NEXT: inspect Docker healthcheck output; App restart alone is unlikely to repair a persistent unhealthy healthcheck.\n'
      ;;
  esac

  case "${app_state}" in
    CRASHED | DEPLOYING | STOPPED | MISSING)
      failures=$((failures + 1))
      ;;
  esac
done <"${tmp}/selected.txt"

printf '\nSUMMARY problematic_apps=%d\n' "${failures}"
((failures == 0))
