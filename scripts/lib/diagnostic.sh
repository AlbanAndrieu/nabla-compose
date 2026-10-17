# shellcheck shell=bash
# Shared bootstrap for compact interactive diagnostics.
#
# scripts/run-diagnostic.sh owns log capture, counters, summaries and exit-code
# propagation. This library only decides whether the current operator script
# should delegate to that wrapper.

nabla_diagnostic_maybe_wrap() {
  local script_path="${1:?diagnostic script path is required}"
  shift
  local script_dir wrapper

  if [[ "${NABLA_DIAGNOSTIC_WRAPPED:-0}" == "1" ||
        "${DIAGNOSTIC_FULL_OUTPUT:-0}" == "1" ]]; then
    return 0
  fi
  if [[ ! -t 1 && "${DIAGNOSTIC_COMPACT_OUTPUT:-0}" != "1" ]]; then
    return 0
  fi

  script_dir="$(cd -- "$(dirname -- "${script_path}")" && pwd)"
  wrapper="$(dirname -- "${script_dir}")/run-diagnostic.sh"
  # Invoke through bash so a checkout that lost Git exec bits still works.
  [[ -r "${wrapper}" ]] || {
    printf 'ERROR: diagnostic wrapper is missing or unreadable: %s\n' "${wrapper}" >&2
    return 2
  }

  exec bash "${wrapper}" "${script_path}" "$@"
}
