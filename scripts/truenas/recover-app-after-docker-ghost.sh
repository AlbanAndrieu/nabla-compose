#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

MODE="${1:---check}"
APP="${2:-}"
ALLOW_ACTIVE="${NABLA_GHOST_RECOVERY_ALLOW_ACTIVE:-false}"
ORPHAN_HELPER="${NABLA_ORPHAN_SHIM_DIAGNOSTIC:-${SCRIPT_DIR}/diagnose-docker-orphan-shims.sh}"
CALL_TIMEOUT="${NABLA_MIDCLT_TIMEOUT_SECONDS:-180}"
APP_JOB_TIMEOUT="${NABLA_APP_JOB_TIMEOUT_SECONDS:-900}"

usage() {
  cat <<'EOF'
usage:
  sudo bash scripts/truenas/recover-app-after-docker-ghost.sh --check [app]
  sudo bash scripts/truenas/recover-app-after-docker-ghost.sh --recover-app <app>

--check
  Read-only ghost matrix. With an App id, restrict output to that App.

--recover-app
  Bounded recovery for one TrueNAS App. It tries supported app.stop first,
  then recovers only Pid=0 Running/Restarting containers with exactly one
  matching containerd shim inside that App project, and retries app.stop.
  RUNNING/DEPLOYING Apps are refused unless
  NABLA_GHOST_RECOVERY_ALLOW_ACTIVE=true.

The helper never restarts Docker/containerd and never kills by process pattern.
EOF
}

case "${MODE}" in
  --check | --recover-app) ;;
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
require_commands midclt jq docker pgrep awk timeout grep
[[ -f "${ORPHAN_HELPER}" ]] || fail "orphan shim helper not found: ${ORPHAN_HELPER}"

midclt_bounded() {
  timeout "${CALL_TIMEOUT}" midclt call "$@"
}

app_state() {
  local app="$1"
  midclt_bounded app.query "[[\"id\",\"=\",\"${app}\"]]" |
    jq -r 'if length == 1 then .[0].state else "MISSING" end'
}

find_shim_pids() {
  local cid="$1"
  pgrep -af containerd-shim-runc-v2 |
    awk -v cid="${cid}" 'index($0, "-id " cid) {print $1}'
}

container_rows() {
  local filter_app="${1:-}" cid row project app
  while IFS= read -r cid; do
    [[ -n "${cid}" ]] || continue
    row="$(docker inspect "${cid}" | jq -c '.[0] | {
      id:.Id,
      name:(.Name|ltrimstr("/")),
      project:(.Config.Labels["com.docker.compose.project"] // ""),
      running:(.State.Running // false),
      restarting:(.State.Restarting // false),
      status:(.State.Status // "unknown"),
      pid:(.State.Pid // 0)
    }')"
    project="$(jq -r '.project' <<<"${row}")"
    app="${project#ix-}"
    [[ -z "${filter_app}" || "${app}" == "${filter_app}" ]] || continue
    jq -c --arg app "${app}" '. + {app:$app}' <<<"${row}"
  done < <(docker ps -aq)
}

print_matrix() {
  local filter_app="${1:-}" row app cid name status running restarting pid
  local -a shims=()
  printf 'APP\tCONTAINER\tAPP_STATE\tDOCKER_STATE\tRUNNING\tRESTARTING\tPID\tSHIMS\n'
  while IFS= read -r row; do
    app="$(jq -r '.app' <<<"${row}")"
    cid="$(jq -r '.id' <<<"${row}")"
    name="$(jq -r '.name' <<<"${row}")"
    status="$(jq -r '.status' <<<"${row}")"
    running="$(jq -r '.running' <<<"${row}")"
    restarting="$(jq -r '.restarting' <<<"${row}")"
    pid="$(jq -r '.pid' <<<"${row}")"
    [[ "${pid}" == "0" && ( "${running}" == "true" || "${restarting}" == "true" ) ]] || continue
    mapfile -t shims < <(find_shim_pids "${cid}")
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n'       "${app:-UNKNOWN}" "${name}" "$(app_state "${app}")" "${status}"       "${running}" "${restarting}" "${pid}" "${#shims[@]}"
  done < <(container_rows "${filter_app}")
}

if [[ "${MODE}" == "--check" ]]; then
  print_matrix "${APP}"
  exit 0
fi

[[ -n "${APP}" ]] || { usage; fail "--recover-app requires an App id"; }

state="$(app_state "${APP}")"
case "${state}" in
  STOPPED | CRASHED | ERROR) ;;
  RUNNING | DEPLOYING)
    [[ "${ALLOW_ACTIVE}" == "true" ]] ||
      fail "${APP}: state=${state}; refuse active App recovery unless NABLA_GHOST_RECOVERY_ALLOW_ACTIVE=true"
    warn "${APP}: explicitly allowing active state ${state} for controlled quiesce"
    ;;
  *)
    fail "${APP}: unsupported middleware state=${state}"
    ;;
esac

printf 'Attempting supported stop first: app=%s state=%s\n' "${APP}" "${state}"
if timeout "${APP_JOB_TIMEOUT}" midclt call -j app.stop "${APP}" >/dev/null; then
  ok "${APP}: supported app.stop succeeded without shim recovery"
else
  warn "${APP}: app.stop failed; evaluating only exact ghosts owned by ix-${APP}"
  mapfile -t ghosts < <(
    container_rows "${APP}" |
      jq -r 'select(.pid == 0 and (.running == true or .restarting == true)) | .name'
  )
  (("${#ghosts[@]}" > 0)) ||
    fail "${APP}: app.stop failed but no Pid=0 Running/Restarting project ghost was found"

  ambiguous=0
  recoverable=()
  for container in "${ghosts[@]}"; do
    cid="$(docker inspect "${container}" | jq -r '.[0].Id')"
    mapfile -t shims < <(find_shim_pids "${cid}")
    printf 'ghost app=%s container=%s shims=%s\n' "${APP}" "${container}" "${#shims[@]}"
    if (("${#shims[@]}" == 1)); then
      recoverable+=("${container}")
    else
      ambiguous=1
    fi
  done

  ((ambiguous == 0)) ||
    fail "${APP}: at least one ghost has zero/multiple shims; no automatic shim recovery performed"

  for container in "${recoverable[@]}"; do
    bash "${ORPHAN_HELPER}" --recover "${container}"
  done

  printf 'Retrying supported stop after exact ghost recovery: app=%s\n' "${APP}"
  timeout "${APP_JOB_TIMEOUT}" midclt call -j app.stop "${APP}" >/dev/null ||
    fail "${APP}: app.stop still failed after bounded ghost recovery"
fi

state="$(app_state "${APP}")"
[[ "${state}" == "STOPPED" ]] ||
  fail "${APP}: final middleware state=${state}, expected STOPPED"

if docker ps -aq --filter "label=com.docker.compose.project=ix-${APP}" | grep -q .; then
  docker ps -a --filter "label=com.docker.compose.project=ix-${APP}"     --format '  {{.Names}}\t{{.Status}}' >&2
  fail "${APP}: project containers remain after successful app.stop"
fi

ok "${APP}: STOPPED with no remaining ix-${APP} containers"
