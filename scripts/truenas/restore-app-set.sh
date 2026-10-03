#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

MODE="${1:---check}"
shift || true

APPS_FILE=""
NAME="restore"
REPO_ROOT="${NABLA_REPO_ROOT:-/mnt/cpool/compose/nabla-compose}"
STATE_ROOT="${NABLA_RESTORE_STATE_ROOT:-/mnt/cpool/var/nabla/restore}"
PLANNER="${NABLA_RESTORE_PLANNER:-${SCRIPT_DIR}/plan-app-lifecycle-order.py}"
HEALTH_GATE="${NABLA_APP_HEALTH_GATE:-${SCRIPT_DIR}/verify-app-runtime-health.sh}"
OPENSEARCH_PERMISSIONS="${NABLA_OPENSEARCH_PERMISSIONS_HELPER:-${SCRIPT_DIR}/repair-opensearch-security-permissions.sh}"
DOCKER_PROXY_NETWORK="${NABLA_DOCKER_PROXY_NETWORK_HELPER:-${SCRIPT_DIR}/ensure-docker-socket-proxy-intranet.sh}"
PIHOLE_SYNC_GATE="${NABLA_PIHOLE_SYNC_GATE:-${SCRIPT_DIR}/verify-pihole-dns-sync.sh}"
APP_JOB_TIMEOUT="${NABLA_APP_JOB_TIMEOUT_SECONDS:-900}"
APP_WAIT="${NABLA_APP_START_WAIT_SECONDS:-600}"
POLL_SECONDS="${NABLA_APP_START_POLL_SECONDS:-5}"
LOG_TAIL="${NABLA_APP_DIAGNOSTIC_LOG_TAIL:-80}"

usage() {
  cat <<'EOF'
usage:
  sudo bash scripts/truenas/restore-app-set.sh --check --apps-file <path> [--name <label>]
  sudo bash scripts/truenas/restore-app-set.sh --apply --apps-file <path> [--name <label>]

Reads one TrueNAS App id per line. Blank lines and # comments are ignored.

--check
  Read-only: validate the App set against app.query, generate the topology-aware
  plan under /tmp, and print current states plus start waves.

--apply
  Persist a restore transaction under /mnt/cpool/var/nabla/restore, then start
  Apps wave-by-wave. Already RUNNING/DEPLOYING Apps are reused. CRASHED/ERROR
  Apps fail closed. Later waves are blocked by required failures.

Environment:
  NABLA_APP_START_WAIT_OVERRIDES="opensearch=1200 clickhouse=900 ..."
EOF
}

case "${MODE}" in
  --check | --apply) ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

while (($#)); do
  case "$1" in
    --apps-file)
      APPS_FILE="${2:-}"
      shift 2
      ;;
    --name)
      NAME="${2:-restore}"
      shift 2
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

require_root "run as root on TrueNAS"
require_commands midclt jq docker python3 timeout sed awk sort grep date install
[[ -n "${APPS_FILE}" ]] || fail "--apps-file is required"
[[ -r "${APPS_FILE}" ]] || fail "Apps file is not readable: ${APPS_FILE}"
[[ -f "${PLANNER}" ]] || fail "planner not found: ${PLANNER}"
[[ -f "${HEALTH_GATE}" ]] || fail "health gate not found: ${HEALTH_GATE}"
[[ -f "${OPENSEARCH_PERMISSIONS}" ]] || fail "OpenSearch permissions helper not found: ${OPENSEARCH_PERMISSIONS}"
[[ -f "${DOCKER_PROXY_NETWORK}" ]] || fail "Docker proxy network helper not found: ${DOCKER_PROXY_NETWORK}"
[[ -f "${PIHOLE_SYNC_GATE}" ]] || fail "Pi-hole sync gate not found: ${PIHOLE_SYNC_GATE}"
[[ -f "${REPO_ROOT}/catalog/services.json" ]] || fail "services catalog missing"
[[ -f "${REPO_ROOT}/catalog/service-topology.json" ]] || fail "topology catalog missing"

for value in APP_JOB_TIMEOUT APP_WAIT POLL_SECONDS LOG_TAIL; do
  current="${!value}"
  [[ "${current}" =~ ^[1-9][0-9]*$ ]] || fail "${value} must be a positive integer"
done

mapfile -t APPS < <(
  awk '
    {
      sub(/[[:space:]]*#.*/, "")
      gsub(/^[[:space:]]+|[[:space:]]+$/, "")
      if (length($0)) print $0
    }
  ' "${APPS_FILE}" | sort -u
)

(("${#APPS[@]}" > 0)) || fail "Apps file contains no App ids"

for app in "${APPS[@]}"; do
  [[ "${app}" =~ ^[a-z0-9][a-z0-9._-]*$ ]] ||
    fail "invalid App id in ${APPS_FILE}: ${app}"
done

stamp="$(date +%Y%m%d-%H%M%S)"
if [[ "${MODE}" == "--apply" ]]; then
  STATE_DIR="${STATE_ROOT}/${stamp}-${NAME}"
  install -d -m 700 "${STATE_ROOT}" "${STATE_DIR}"
else
  STATE_DIR="$(mktemp -d "/tmp/nabla-restore-${NAME}.XXXXXX")"
  trap 'rm -rf "${STATE_DIR}"' EXIT
fi

APPS_JSON="${STATE_DIR}/apps-current.json"
PLAN_JSON="${STATE_DIR}/restore-plan.json"
midclt call app.query >"${APPS_JSON}"

known_apps="$(
  jq -r '.[].id' "${APPS_JSON}"
)"
for app in "${APPS[@]}"; do
  grep -Fxq -- "${app}" <<<"${known_apps}" ||
    fail "TrueNAS App not found in app.query: ${app}"
done

include_apps="${APPS[*]}"
python3 "${PLANNER}"   --apps "${APPS_JSON}"   --states __NONE__   --include-apps "${include_apps}"   --services "${REPO_ROOT}/catalog/services.json"   --topology "${REPO_ROOT}/catalog/service-topology.json"   --pretty >"${PLAN_JSON}"

printf 'Restore plan: %s\n' "${PLAN_JSON}"
jq '{selected_apps,unmapped_apps,start_waves,lifecycle_phase_by_app}' "${PLAN_JSON}"

printf '\nCurrent App states:\n'
for app in "${APPS[@]}"; do
  state="$(
    jq -r --arg app "${app}"       '.[] | select(.id==$app) | .state' "${APPS_JSON}"
  )"
  printf '  %-28s %s\n' "${app}" "${state}"
done

[[ "${MODE}" == "--apply" ]] || exit 0

printf 'PREPARED\n' >"${STATE_DIR}/phase"
printf '%s\n' "${APPS[@]}" >"${STATE_DIR}/apps.txt"

app_state() {
  local app="$1"
  midclt call app.query "[[\"id\",\"=\",\"${app}\"]]" |
    jq -r 'if length==1 then .[0].state else "UNKNOWN" end'
}

app_timeout() {
  local app="$1" key value pair
  local -a overrides=()
  read -r -a overrides <<<"${NABLA_APP_START_WAIT_OVERRIDES:-}"
  for pair in "${overrides[@]}"; do
    key="${pair%%=*}"
    value="${pair#*=}"
    if [[ "${key}" == "${app}" && "${value}" =~ ^[1-9][0-9]*$ ]]; then
      printf '%s\n' "${value}"
      return
    fi
  done
  printf '%s\n' "${APP_WAIT}"
}

diagnose_app() {
  local app="$1" project id
  project="ix-${app}"

  printf 'DIAG app=%s state=%s\n' "${app}" "$(app_state "${app}")" >&2
  midclt call app.query "[[\"id\",\"=\",\"${app}\"]]" |
    jq 'if length==1 then .[0] | {id,state,active_workloads,upgrade_available} else . end' >&2 || true

  mapfile -t ids < <(docker ps -aq --filter "label=com.docker.compose.project=${project}")
  for id in "${ids[@]}"; do
    docker inspect "${id}" |
      jq -r '.[0] | "  container=\(.Name|ltrimstr("/")) status=\(.State.Status // "unknown") health=\(.State.Health.Status // "none") running=\(.State.Running // false) restarting=\(.State.Restarting // false) pid=\(.State.Pid // 0) restarts=\(.RestartCount // 0) exit=\(.State.ExitCode // 0) error=\(.State.Error // "")"' >&2 || true
    printf '  recent logs (%s lines):\n' "${LOG_TAIL}" >&2
    docker logs --tail "${LOG_TAIL}" "${id}" 2>&1 | sed 's/^/    /' >&2 || true
  done
}

wait_running() {
  local app="$1" deadline state timeout_seconds
  timeout_seconds="$(app_timeout "${app}")"
  deadline=$((SECONDS + timeout_seconds))
  while ((SECONDS < deadline)); do
    state="$(app_state "${app}")"
    case "${state}" in
      RUNNING) return 0 ;;
      CRASHED | ERROR)
        warn "${app}: converged to ${state}"
        return 1
        ;;
    esac
    sleep "${POLL_SECONDS}"
  done
  warn "${app}: RUNNING timeout after ${timeout_seconds}s; final state=$(app_state "${app}")"
  return 1
}

prepare_app_storage() {
  local app="$1"
  case "${app}" in
    opensearch)
      printf 'PREPARE %s storage ownership\n' "${app}"
      bash "${OPENSEARCH_PERMISSIONS}" --apply
      ;;
  esac
}

prepare_app_runtime() {
  local app="$1"
  case "${app}" in
    docker-socket-proxy)
      printf 'PREPARE %s shared intranet attachment\n' "${app}"
      bash "${DOCKER_PROXY_NETWORK}" --apply
      ;;
  esac
}

verify_app_contracts() {
  local app="$1"
  case "${app}" in
    pihole)
      printf 'VERIFY %s DNS sync dependency contract\n' "${app}"
      bash "${PIHOLE_SYNC_GATE}"
      ;;
  esac
}

restore_app() {
  local app="$1" state timeout_seconds
  state="$(app_state "${app}")"
  case "${state}" in
    RUNNING)
      printf 'VERIFY %s already RUNNING\n' "${app}"
      ;;
    DEPLOYING)
      printf 'WAIT %s already DEPLOYING\n' "${app}"
      ;;
    STOPPED)
      prepare_app_storage "${app}"
      printf 'START %s\n' "${app}"
      timeout "${APP_JOB_TIMEOUT}" midclt call -j app.start "${app}" >/dev/null ||
        {
          diagnose_app "${app}"
          return 1
        }
      ;;
    CRASHED | ERROR)
      warn "${app}: refusing blind restart from state=${state}"
      diagnose_app "${app}"
      return 1
      ;;
    *)
      warn "${app}: unexpected state=${state}; waiting without duplicate app.start"
      ;;
  esac

  wait_running "${app}" || {
    diagnose_app "${app}"
    return 1
  }

  prepare_app_runtime "${app}" || {
    diagnose_app "${app}"
    return 1
  }

  timeout_seconds="$(app_timeout "${app}")"
  NABLA_APP_HEALTH_TIMEOUT_SECONDS="${timeout_seconds}"     bash "${HEALTH_GATE}" "${app}" || {
      diagnose_app "${app}"
      return 1
    }

  verify_app_contracts "${app}" || {
    diagnose_app "${app}"
    return 1
  }

  printf 'READY %s\n' "${app}"
}

wave_count="$(jq '.start_waves | length' "${PLAN_JSON}")"
total_failures=0

printf 'RESTORING\n' >"${STATE_DIR}/phase"
for ((i=0; i<wave_count; i++)); do
  mapfile -t wave < <(jq -r --argjson i "${i}" '.start_waves[$i][]' "${PLAN_JSON}")
  blocking_failures=0
  non_blocking_failures=0

  printf '\nRESTORE WAVE %s/%s (%s Apps)\n' "$((i+1))" "${wave_count}" "${#wave[@]}"
  for app in "${wave[@]}"; do
    if restore_app "${app}"; then
      continue
    fi

    total_failures=$((total_failures + 1))
    if jq -e --arg app "${app}"       '(.lifecycle_phase_by_app[$app].blocksLaterWaves // true) == true'       "${PLAN_JSON}" >/dev/null; then
      blocking_failures=$((blocking_failures + 1))
    else
      non_blocking_failures=$((non_blocking_failures + 1))
      warn "${app}: non-blocking failure recorded"
    fi
  done

  if ((blocking_failures > 0 && i + 1 < wave_count)); then
    printf 'FAILED\n' >"${STATE_DIR}/phase"
    fail "dependency barrier: ${blocking_failures} blocking App(s) failed in wave $((i+1))"
  fi

  if ((non_blocking_failures > 0)); then
    warn "wave $((i+1)): ${non_blocking_failures} non-blocking failure(s)"
  fi
done

if ((total_failures > 0)); then
  printf 'FAILED\n' >"${STATE_DIR}/phase"
  fail "${total_failures} App(s) failed restore"
fi

printf 'RESTORED\n' >"${STATE_DIR}/phase"
ok "restore set is RUNNING and container-stable: ${STATE_DIR}"
