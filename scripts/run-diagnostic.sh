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
log_file="${DIAGNOSTIC_LOG_FILE:-${log_dir}/${name}-${timestamp}.log}"
summary_lines="${DIAGNOSTIC_SUMMARY_LINES:-12}"

install -d -m 700 "${log_dir}"
install -m 600 /dev/null "${log_file}"

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
