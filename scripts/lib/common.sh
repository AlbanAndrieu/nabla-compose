# shellcheck shell=bash

# Shared, side-effect-free shell primitives for operator scripts.
# Keep this file small: domain logic belongs in dedicated libraries/scripts.
# Self-contained on purpose: reboot bundles copy this file alone.

# Decorate only interactive terminals. Logs, pipes, CI and NO_COLOR keep the
# stable plain-text prefixes that tests and log parsers rely on.
nabla_tty_style() {
  local fd="$1" color="$2" icon="$3" label="$4"
  shift 4
  if [[ -t "${fd}" && -z "${NO_COLOR+x}" && "${TERM:-dumb}" != dumb ]]; then
    case "${NABLA_UI_ASCII:-0}:${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
      0:*UTF-8* | 0:*utf8* | 0:*utf-8*) label="${icon} ${label}" ;;
      *) ;;
    esac
    printf '\033[%sm%s\033[0m %s\n' "${color}" "${label}" "$*"
  else
    printf '%s %s\n' "${label}" "$*"
  fi
}

fail() {
  nabla_tty_style 2 '1;31' '❌' 'ERROR:' "$*" >&2
  exit 1
}

warn() {
  nabla_tty_style 2 33 '⚠️ ' 'WARN:' "$*" >&2
}

ok() {
  nabla_tty_style 1 32 '✅' 'OK:' "$*"
}

info() {
  nabla_tty_style 1 36 'ℹ️ ' 'INFO:' "$*"
}

section() {
  printf '\n'
  nabla_tty_style 1 '1;34' '🔷' '==>' "$*"
}

require_root() {
  [[ "${EUID}" -eq 0 ]] || fail "${1:-run as root}"
}

require_commands() {
  local required
  for required in "$@"; do
    command -v "${required}" >/dev/null 2>&1 || fail "${required} is required"
  done
}
