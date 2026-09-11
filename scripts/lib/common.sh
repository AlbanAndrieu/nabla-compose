# shellcheck shell=bash

# Shared, side-effect-free shell primitives for operator scripts.
# Keep this file small: domain logic belongs in dedicated libraries/scripts.

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf 'WARN: %s\n' "$*" >&2
}

ok() {
  printf 'OK: %s\n' "$*"
}

require_root() {
  [[ "${EUID}" -eq 0 ]] || fail "run as root"
}

require_commands() {
  local required
  for required in "$@"; do
    command -v "${required}" >/dev/null 2>&1 || fail "${required} is required"
  done
}
