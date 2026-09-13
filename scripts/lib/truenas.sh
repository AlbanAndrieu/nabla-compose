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
