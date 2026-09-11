#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

MODE="${1:---check}"
STATE_ROOT="${NABLA_REBOOT_STATE_ROOT:-/mnt/cpool/var/nabla/reboot}"
CALL_TIMEOUT="${NABLA_MIDCLT_TIMEOUT_SECONDS:-180}"
APP_JOB_TIMEOUT="${NABLA_APP_JOB_TIMEOUT_SECONDS:-900}"
APP_WAIT="${NABLA_APP_START_WAIT_SECONDS:-600}"
POLL_SECONDS="${NABLA_APP_POLL_SECONDS:-5}"
LOG_TAIL="${NABLA_APP_DIAGNOSTIC_LOG_TAIL:-80}"

usage() {
  cat <<'EOF'
usage: sudo bash scripts/truenas/reconcile-reboot-resume.sh [--check|--apply]

--check  Read-only comparison of the frozen reboot resume manifest with live Apps.
--apply  Start missing Apps in frozen topology waves, aggregating failures inside
         each wave and stopping before the next dependency wave if one fails.

Timeouts:
  NABLA_MIDCLT_TIMEOUT_SECONDS      simple middleware calls, default 180
  NABLA_APP_JOB_TIMEOUT_SECONDS     app.start job, default 900
  NABLA_APP_START_WAIT_SECONDS      post-job RUNNING acceptance, default 600
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

require_root "run as root on TrueNAS"
require_commands midclt jq docker timeout awk

for value in CALL_TIMEOUT APP_JOB_TIMEOUT APP_WAIT POLL_SECONDS LOG_TAIL; do
  current="${!value}"
  [[ "${current}" =~ ^[1-9][0-9]*$ ]] || fail "${value} must be a positive integer"
done

midclt_bounded() {
  timeout "${CALL_TIMEOUT}" midclt call "$@"
}

latest_state_dir() {
  [[ -f "${STATE_ROOT}/latest" ]] || fail "no reboot state manifest at ${STATE_ROOT}/latest"
  local dir
  dir="$(cat "${STATE_ROOT}/latest")"
  [[ -d "${dir}" ]] || fail "recorded reboot state directory is missing: ${dir}"
  [[ -f "${dir}/resume-plan.json" ]] || fail "resume plan missing: ${dir}/resume-plan.json"
  [[ -f "${dir}/boot-id-before" ]] || fail "boot id missing: ${dir}/boot-id-before"
  printf '%s\n' "${dir}"
}

app_json() {
  local app="$1"
  midclt_bounded app.query "[[\"id\",\"=\",\"${app}\"]]"
}

app_state() {
  local app="$1"
  app_json "${app}" | jq -r 'if length == 1 then .[0].state else "UNKNOWN" end'
}

app_timeout() {
  local app="$1" key value pair
  for pair in ${NABLA_APP_START_WAIT_OVERRIDES:-}; do
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
  local app="$1" state project id
  local -a ids=()

  state="$(app_state "${app}")"
  project="ix-${app}"
  printf 'DIAG app=%s state=%s\n' "${app}" "${state}" >&2
  app_json "${app}" |
    jq 'if length == 1 then .[0] | {id,state,active_workloads,upgrade_available} else . end' >&2 || true

  mapfile -t ids < <(docker ps -aq --filter "label=com.docker.compose.project=${project}")
  if ((${#ids[@]} == 0)); then
    warn "${app}: no Docker containers found for compose project ${project}"
    return 0
  fi

  for id in "${ids[@]}"; do
    docker inspect "${id}" |
      jq -r '.[0] | "  container=\(.Name|ltrimstr("/")) status=\(.State.Status // "unknown") health=\(.State.Health.Status // "none") running=\(.State.Running // false) restarting=\(.State.Restarting // false) pid=\(.State.Pid // 0) restarts=\(.RestartCount // 0) exit=\(.State.ExitCode // 0) error=\(.State.Error // "")"' >&2 || true
    printf '  recent logs (%s lines):\n' "${LOG_TAIL}" >&2
    docker logs --tail "${LOG_TAIL}" "${id}" 2>&1 | sed 's/^/    /' >&2 || true
  done
}

wait_running() {
  local app="$1" wait_seconds deadline state
  wait_seconds="$(app_timeout "${app}")"
  deadline=$((SECONDS + wait_seconds))
  while ((SECONDS < deadline)); do
    state="$(app_state "${app}")"
    case "${state}" in
      RUNNING) return 0 ;;
      CRASHED | ERROR)
        warn "${app}: converged to ${state} before timeout"
        return 1
        ;;
    esac
    sleep "${POLL_SECONDS}"
  done
  state="$(app_state "${app}")"
  warn "${app}: did not reach RUNNING within ${wait_seconds}s; final state=${state}"
  return 1
}

start_or_wait_app() {
  local app="$1" state
  state="$(app_state "${app}")"
  case "${state}" in
    RUNNING)
      printf 'SKIP %s already RUNNING\n' "${app}"
      return 0
      ;;
    STOPPED)
      printf 'START %s\n' "${app}"
      if ! timeout "${APP_JOB_TIMEOUT}" midclt call -j app.start "${app}" >/dev/null; then
        warn "${app}: app.start client/job did not complete within ${APP_JOB_TIMEOUT}s"
        diagnose_app "${app}"
        return 1
      fi
      ;;
    DEPLOYING)
      printf 'WAIT %s already DEPLOYING\n' "${app}"
      ;;
    CRASHED | ERROR)
      warn "${app}: state=${state}; refusing blind automatic restart"
      diagnose_app "${app}"
      return 1
      ;;
    *)
      warn "${app}: unexpected pre-resume state=${state}; waiting rather than issuing duplicate app.start"
      ;;
  esac

  if wait_running "${app}"; then
    printf 'READY %s\n' "${app}"
    return 0
  fi
  diagnose_app "${app}"
  return 1
}

state_dir="$(latest_state_dir)"
before_boot_id="$(cat "${state_dir}/boot-id-before")"
current_boot_id="$(midclt_bounded system.boot_id | tr -d '"')"
[[ "${current_boot_id}" != "${before_boot_id}" ]] || fail "refusing resume reconciliation before an actual reboot"

ready="$(midclt_bounded system.ready | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
[[ "${ready}" == "true" ]] || fail "TrueNAS system.ready is not true"

printf 'Reboot resume reconciliation mode=%s manifest=%s\n' "${MODE}" "${state_dir}"
wave_count="$(jq '.start_waves | length' "${state_dir}/resume-plan.json")"
total_failures=0

for ((i=0; i<wave_count; i++)); do
  mapfile -t wave < <(jq -r --argjson i "${i}" '.start_waves[$i][]' "${state_dir}/resume-plan.json")
  wave_failures=0
  printf '\nRESUME WAVE %s/%s (%s Apps)\n' "$((i + 1))" "${wave_count}" "${#wave[@]}"

  for app in "${wave[@]}"; do
    state="$(app_state "${app}")"
    if [[ "${MODE}" == "--check" ]]; then
      printf '%-28s %s\n' "${app}" "${state}"
      if [[ "${state}" != "RUNNING" ]]; then
        wave_failures=$((wave_failures + 1))
        total_failures=$((total_failures + 1))
      fi
      continue
    fi

    if ! start_or_wait_app "${app}"; then
      wave_failures=$((wave_failures + 1))
      total_failures=$((total_failures + 1))
    fi
  done

  if ((wave_failures > 0)); then
    warn "wave $((i + 1)) has ${wave_failures} App failure(s)"
    if ((i + 1 < wave_count)); then
      fail "dependency barrier: refusing to start later waves until the current wave converges"
    fi
  fi
done

if ((total_failures > 0)); then
  fail "${total_failures} saved App(s) are not RUNNING"
fi

if [[ "${MODE}" == "--apply" ]]; then
  printf 'RESUMED\n' >"${state_dir}/phase"
fi
ok "all Apps from the frozen reboot resume manifest are RUNNING"
