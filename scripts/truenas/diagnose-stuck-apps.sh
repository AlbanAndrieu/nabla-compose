#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMMON_LIB="${SCRIPT_DIR}/../lib/common.sh"
if [[ ! -r "${COMMON_LIB}" ]]; then
  COMMON_LIB="${NABLA_REPO_ROOT:-/mnt/cpool/compose/nabla-compose}/scripts/lib/common.sh"
fi
# shellcheck source=../lib/common.sh
source "${COMMON_LIB}"

MODE="${1:---check}"
shift || true

APP_QUERY_TIMEOUT="${NABLA_STUCK_APP_QUERY_TIMEOUT_SECONDS:-90}"
LOG_TAIL="${NABLA_STUCK_APP_LOG_TAIL:-40}"
TOPOLOGY="${NABLA_TOPOLOGY_FILE:-/mnt/cpool/compose/nabla-compose/catalog/service-topology.json}"
REBOOT_STATE_ROOT="${NABLA_REBOOT_STATE_ROOT:-/mnt/cpool/var/nabla/reboot}"
REBOOT_STATE_DIR="${NABLA_REBOOT_STATE_DIR:-}"
APP_FILTERS=()

usage() {
  cat <<'EOF'
usage:
  sudo bash scripts/truenas/diagnose-stuck-apps.sh --check [--app APP ...]

Read-only post-reboot diagnostic for TrueNAS Apps that are CRASHED, ERROR,
DEPLOYING or STOPPED. It correlates:
- app.query lifecycle state
- recent app lifecycle jobs
- Docker Compose project containers
- health/restart/exit state
- bounded recent logs for unhealthy/restarting/non-zero-exit containers
- the frozen reboot manifest when available, separating pre-existing/intentional
  debt from Apps that were expected to resume

With --app, only the named Apps are inspected.
Required catalog dependencies are printed with their current TrueNAS state when resolvable.
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
require_commands timeout midclt jq docker grep tail sed head sort mktemp cat
[[ -r "${TOPOLOGY}" ]] || fail "topology catalog is not readable: ${TOPOLOGY}"

for value in APP_QUERY_TIMEOUT LOG_TAIL; do
  current="${!value}"
  [[ "${current}" =~ ^[1-9][0-9]*$ ]] || fail "${value} must be a positive integer"
done

tmp="$(mktemp -d /tmp/nabla-stuck-apps.XXXXXX)"
trap 'rm -rf "${tmp}"' EXIT
apps_json="${tmp}/apps.json"
jobs_json="${tmp}/jobs.json"

resolve_reboot_manifest() {
  local candidate=""

  if [[ -n "${REBOOT_STATE_DIR}" ]]; then
    candidate="${REBOOT_STATE_DIR}"
  elif [[ -f "${REBOOT_STATE_ROOT}/latest" ]]; then
    candidate="$(cat "${REBOOT_STATE_ROOT}/latest")"
  fi

  if [[ -n "${candidate}" &&
    -d "${candidate}" &&
    -f "${candidate}/apps-before.json" &&
    -f "${candidate}/resume-apps.txt" &&
    -f "${candidate}/intentional-stopped.txt" &&
    -f "${candidate}/preexisting-failed.txt" ]]; then
    REBOOT_STATE_DIR="${candidate}"
  else
    REBOOT_STATE_DIR=""
  fi
}

reboot_context() {
  local app="$1" before_state="UNKNOWN" context="manifest-unavailable"

  if [[ -n "${REBOOT_STATE_DIR}" ]]; then
    before_state="$(
      jq -r --arg app "${app}"         '[.[] | select(.id == $app) | .state][0] // "UNKNOWN"'         "${REBOOT_STATE_DIR}/apps-before.json"
    )"
    if grep -Fxq -- "${app}" "${REBOOT_STATE_DIR}/preexisting-failed.txt"; then
      context="preexisting-failed"
    elif grep -Fxq -- "${app}" "${REBOOT_STATE_DIR}/intentional-stopped.txt"; then
      context="intentional-stopped"
    elif grep -Fxq -- "${app}" "${REBOOT_STATE_DIR}/resume-apps.txt"; then
      context="expected-resume"
    else
      context="untracked"
    fi
  fi

  printf '%s\t%s\n' "${context}" "${before_state}"
}

resolve_reboot_manifest

timeout "${APP_QUERY_TIMEOUT}" midclt call app.query >"${apps_json}" ||
  fail "app.query did not respond within ${APP_QUERY_TIMEOUT}s"
timeout "${APP_QUERY_TIMEOUT}" midclt call core.get_jobs >"${jobs_json}" ||
  fail "core.get_jobs did not respond within ${APP_QUERY_TIMEOUT}s"

if (("${#APP_FILTERS[@]}" > 0)); then
  printf '%s\n' "${APP_FILTERS[@]}" >"${tmp}/selected.txt"
else
  jq -r '
    .[]
    | select(
        .state == "CRASHED"
        or .state == "ERROR"
        or .state == "DEPLOYING"
        or .state == "STOPPED"
      )
    | .id
  ' "${apps_json}" |
    sort -u >"${tmp}/selected.txt"
fi

if [[ ! -s "${tmp}/selected.txt" ]]; then
  ok "no CRASHED/ERROR/DEPLOYING/STOPPED Apps"
  exit 0
fi

failures=0
deferred=0
problematic=0
while IFS= read -r app; do
  [[ -n "${app}" ]] || continue
  app_state="$(
    jq -r --arg app "${app}" '.[] | select(.id == $app) | .state // "MISSING"' "${apps_json}" |
      head -n 1
  )"
  [[ -n "${app_state}" ]] || app_state="MISSING"

  IFS="$(printf '\t')" read -r reboot_class pre_reboot_state < <(reboot_context "${app}")
  printf '\n=== APP %s state=%s ===\n' "${app}" "${app_state}"
  printf 'reboot_context=%s pre_reboot_state=%s manifest=%s\n'     "${reboot_class}" "${pre_reboot_state}" "${REBOOT_STATE_DIR:-unavailable}"

  printf '%s\n' '-- required catalog dependencies --'
  jq -r --arg app "${app}" '
    .nodes as $nodes
    | (
        $nodes
        | map(
            select(
              .id == $app
              or .runtime.appId == $app
              or .sourcePath == ("apps/" + $app + "/compose.yml")
            )
          )
        | map(.id)
      ) as $sources
    | [
        .relations[]?
        | select((.strength // "required") == "required")
        | select(.source as $source | $sources | index($source))
        | .target
      ]
    | unique[]
  ' "${TOPOLOGY}" 2>/dev/null |
    while IFS= read -r dependency; do
      [[ -n "${dependency}" ]] || continue
      if [[ "${dependency}" == "docker" ]]; then
        if docker info >/dev/null 2>&1; then
          printf 'dependency=docker runtime=host-docker state=RUNNING\n'
        else
          printf 'dependency=docker runtime=host-docker state=UNAVAILABLE\n'
        fi
        continue
      fi

      runtime_id="$(
        jq -r --arg dep "${dependency}" '
          (
            .nodes[]?
            | select(.id == $dep)
            | .runtime.appId //
              (
                .sourcePath
                | select(type == "string")
                | capture("^apps/(?<app>[^/]+)/compose[.]yml$").app
              ) //
              .id
          ) // $dep
        ' "${TOPOLOGY}" 2>/dev/null |
          head -n 1
      )"
      dep_state="$(
        jq -r --arg rid "${runtime_id}" '
          [.[] | select(.id == $rid) | .state][0] // "UNRESOLVED"
        ' "${apps_json}"
      )"
      printf 'dependency=%s runtime=%s state=%s\n' "${dependency}" "${runtime_id}" "${dep_state}"
    done

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
      printf 'NEXT: verify /mnt/cpool/langflow/.env.secrets contains a non-empty LANGFLOW_SUPERUSER_PASSWORD before restart.\n'
      ;;
    grafana)
      printf 'NEXT: Loki/Tempo permission failures require bind-root ownership repair before restarting Grafana.\n'
      ;;
    i2p)
      printf 'NEXT: the I2P router healthcheck must listen on 7657; if I2P is intentionally deferred, keep the App STOPPED instead of forcing convergence.\n'
      ;;
    openrag)
      printf 'NEXT: require Langflow and OpenSearch healthy, then run reconcile-openrag-opensearch-secret.sh --check before restarting OpenRAG.\n'
      ;;
    tailscale)
      printf 'NEXT: Tailscale is documented as intentionally deferred; keep it STOPPED unless it has an explicit current consumer.\n'
      ;;
    vaultwarden)
      printf 'NEXT: validate local + canonical HTTPS /api/config with configure-bitwarden-cli-local.sh --check; a public 404 is an ingress/tunnel defect.\n'
      ;;
  esac

  case "${app_state}" in
    CRASHED | ERROR | DEPLOYING | STOPPED | MISSING)
      problematic=$((problematic + 1))
      if [[ "${reboot_class}" == "intentional-stopped" && "${app_state}" == "STOPPED" ]] ||
        [[ "${reboot_class}" == "preexisting-failed" &&
          ("${app_state}" == "CRASHED" || "${app_state}" == "ERROR" || "${app_state}" == "STOPPED") ]]; then
        deferred=$((deferred + 1))
      else
        failures=$((failures + 1))
      fi
      ;;
  esac
done <"${tmp}/selected.txt"

printf '\nSUMMARY problematic_apps=%d regressions=%d deferred=%d\n'   "${problematic}" "${failures}" "${deferred}"
((failures == 0))
