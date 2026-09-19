# shellcheck shell=bash
# Shared read-only TrueNAS middleware/lifecycle helpers.
#
# This file is sourced by operator scripts. Keep diagnostics bounded and never
# emit environment values or Compose payloads that may contain secrets.

truenas_lifecycle_mark() {
  local log_path="${TRUENAS_APP_LIFECYCLE_LOG:-/var/log/app_lifecycle.log}"

  if [[ ! -r "${log_path}" ]]; then
    printf '0\n'
    return 0
  fi

  wc -l <"${log_path}" | tr -d '[:space:]'
  printf '\n'
}

truenas_lifecycle_errors_since() {
  local app_id="${1:?TrueNAS app id is required}"
  local mark="${2:-0}"
  local limit="${3:-40}"
  local log_path="${TRUENAS_APP_LIFECYCLE_LOG:-/var/log/app_lifecycle.log}"
  local current_lines start_line evidence

  [[ "${mark}" =~ ^[0-9]+$ ]] || mark=0
  [[ "${limit}" =~ ^[1-9][0-9]*$ ]] || limit=40

  if [[ ! -r "${log_path}" ]]; then
    printf 'INFO: TrueNAS lifecycle log is not readable: %s\n' "${log_path}" >&2
    return 0
  fi

  current_lines="$(wc -l <"${log_path}" | tr -d '[:space:]')"
  [[ "${current_lines}" =~ ^[0-9]+$ ]] || current_lines=0

  # Log rotation/truncation can make a pre-mutation line mark larger than the
  # current file. In that case inspect the current file rather than silently
  # missing fresh evidence.
  if ((mark > current_lines)); then
    mark=0
  fi
  start_line=$((mark + 1))

  evidence="$({
    tail -n "+${start_line}" "${log_path}" 2>/dev/null || true
  } | grep -F "${app_id}" |
    grep -Ei 'error|fail(ed|ure)?|exception|traceback|critical|unable|cannot|tim(e|ed)[ -]?out' |
    tail -n "${limit}" || true)"

  if [[ -z "${evidence}" ]]; then
    printf 'OK: no new TrueNAS lifecycle error evidence for %s\n' "${app_id}"
    return 0
  fi

  printf 'WARNING: new TrueNAS lifecycle error evidence for %s (max %s lines):\n' \
    "${app_id}" "${limit}" >&2
  printf '%s\n' "${evidence}" >&2
  return 1
}


truenas_app_state() {
  local app_id="${1:?TrueNAS app id is required}"
  midclt call app.query "[[\"id\",\"=\",\"${app_id}\"]]" |
    jq -r 'if length == 1 then .[0].state else "MISSING" end'
}

truenas_reconcile_custom_app() {
  local app_id="${1:?TrueNAS app id is required}"
  local compose_path="${2:?compose path is required}"
  local payload wrapper

  [[ -f "${compose_path}" ]] || {
    printf 'ERROR: missing Compose file: %s\n' "${compose_path}" >&2
    return 1
  }

  if midclt call app.query "[[\"id\",\"=\",\"${app_id}\"]]" |
    jq -e 'length == 1' >/dev/null; then
    payload="$(jq -cn --arg include "${compose_path}" '{
      custom_compose_config: {include: [$include]}
    }')"
    midclt call -j app.update "${app_id}" "${payload}"
  else
    wrapper="$(printf 'include:\n  - %s\n' "${compose_path}")"
    payload="$(jq -cn --arg app_name "${app_id}" --arg compose "${wrapper}" '{
      app_name: $app_name,
      custom_app: true,
      custom_compose_config_string: $compose
    }')"
    midclt call -j app.create "${payload}"
  fi
}

truenas_wait_app_running() {
  local app_id="${1:?TrueNAS app id is required}"
  local timeout_seconds="${2:-600}"
  local poll_seconds="${3:-4}"
  local deadline state
  deadline=$((SECONDS + timeout_seconds))
  while ((SECONDS < deadline)); do
    state="$(truenas_app_state "${app_id}")"
    case "${state}" in
      RUNNING) return 0 ;;
      CRASHED | ERROR | MISSING)
        printf 'ERROR: %s converged to %s\n' "${app_id}" "${state}" >&2
        return 1
        ;;
    esac
    sleep "${poll_seconds}"
  done
  printf 'ERROR: %s did not reach RUNNING within %ss (state=%s)\n'     "${app_id}" "${timeout_seconds}" "$(truenas_app_state "${app_id}")" >&2
  return 1
}
