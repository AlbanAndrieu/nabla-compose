#!/usr/bin/env bash
set -uo pipefail

if (($# < 1)); then
  printf 'usage: %s <diagnostic-script> [args...]\n' "$0" >&2
  exit 2
fi

target="$1"
shift

[[ -f "${target}" ]] || {
  printf 'ERROR: diagnostic script not found: %s\n' "${target}" >&2
  exit 2
}

name="$(basename "${target}")"
name="${name%.sh}"
timestamp="$(date +%Y%m%d-%H%M%S)"
log_dir="${DIAGNOSTIC_LOG_DIR:-/tmp}"
summary_lines="${DIAGNOSTIC_SUMMARY_LINES:-12}"

prepare_log_dir() {
  if [[ ! -e "${log_dir}" ]]; then
    umask 077
    mkdir -p -- "${log_dir}" || {
      printf 'ERROR: cannot create diagnostic log directory: %s\n' "${log_dir}" >&2
      exit 2
    }
    chmod 700 -- "${log_dir}" || {
      printf 'ERROR: cannot secure diagnostic log directory: %s\n' "${log_dir}" >&2
      exit 2
    }
  fi

  [[ -d "${log_dir}" && ! -L "${log_dir}" ]] || {
    printf 'ERROR: diagnostic log directory must be a real directory: %s\n' "${log_dir}" >&2
    exit 2
  }
  [[ -w "${log_dir}" && -x "${log_dir}" ]] || {
    printf 'ERROR: diagnostic log directory is not writable/searchable: %s\n' "${log_dir}" >&2
    exit 2
  }
}

prepare_explicit_log_file() {
  local requested="$1"
  local parent

  parent="$(dirname -- "${requested}")"
  if [[ "${parent}" != "${log_dir}" ]]; then
    printf 'ERROR: DIAGNOSTIC_LOG_FILE must stay inside DIAGNOSTIC_LOG_DIR (%s): %s\n' \
      "${log_dir}" "${requested}" >&2
    exit 2
  fi

  if [[ -L "${requested}" ]]; then
    printf 'ERROR: refusing symlinked diagnostic log file: %s\n' "${requested}" >&2
    exit 2
  fi
  if [[ -e "${requested}" && ! -f "${requested}" ]]; then
    printf 'ERROR: diagnostic log path is not a regular file: %s\n' "${requested}" >&2
    exit 2
  fi

  umask 077
  : >"${requested}" || {
    printf 'ERROR: cannot create diagnostic log file: %s\n' "${requested}" >&2
    exit 2
  }
  chmod 600 -- "${requested}" || {
    printf 'ERROR: cannot secure diagnostic log file: %s\n' "${requested}" >&2
    exit 2
  }
}

prepare_log_dir

if [[ -n "${DIAGNOSTIC_LOG_FILE:-}" ]]; then
  log_file="${DIAGNOSTIC_LOG_FILE}"
  prepare_explicit_log_file "${log_file}"
else
  umask 077
  if ! log_file="$(mktemp "${log_dir%/}/${name}-${timestamp}.XXXXXX.log")"; then
    printf 'ERROR: cannot allocate diagnostic log file in %s\n' "${log_dir}" >&2
    exit 2
  fi
  chmod 600 -- "${log_file}" || {
    printf 'ERROR: cannot secure diagnostic log file: %s\n' "${log_file}" >&2
    exit 2
  }
fi

set +e
NABLA_DIAGNOSTIC_WRAPPED=1 bash "${target}" "$@" >"${log_file}" 2>&1
status=$?
set -e

count_matches() {
  local pattern="$1"
  grep -Ec "${pattern}" "${log_file}" 2>/dev/null || true
}

ok_count="$(count_matches '^(✅|OK:|PASS:)')"
fail_count="$(count_matches '^(❌|ERROR:|FAIL:)')"
warn_count="$(count_matches '^(⚠️|WARN:|WARNING:)')"
skip_count="$(count_matches '^(SKIP:|⏭️)')"

printf '📋 %s: exit=%d ok=%s failed=%s warnings=%s skipped=%s\n' \
  "${name}" "${status}" "${ok_count}" "${fail_count}" "${warn_count}" "${skip_count}"

if ((status != 0 || fail_count > 0 || warn_count > 0)); then
  printf '%s\n' 'Key findings:'
  grep -E '^(❌|ERROR:|FAIL:|⚠️|WARN:|WARNING:)' "${log_file}" 2>/dev/null |
    tail -n "${summary_lines}" |
    sed 's/^/  /' || true
fi

printf 'Detailed report: %s\n' "${log_file}"
exit "${status}"
