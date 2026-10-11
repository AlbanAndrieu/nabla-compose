# shellcheck shell=bash
# Shared operator terminal presentation. Source only; no output on import.
# Never color redirected output, logs, CI, or machine-readable pipelines.
nabla_ui_init() {
  NABLA_UI_RESET='' NABLA_UI_GREEN='' NABLA_UI_YELLOW='' NABLA_UI_RED='' NABLA_UI_BLUE=''
  NABLA_UI_OK='OK' NABLA_UI_WARN='WARN' NABLA_UI_FAIL='FAIL' NABLA_UI_INFO='INFO'
  if [[ -t 1 && -z "${NO_COLOR+x}" && "${TERM:-dumb}" != dumb ]]; then
    NABLA_UI_RESET=$'\033[0m'
    NABLA_UI_GREEN=$'\033[32m'
    NABLA_UI_YELLOW=$'\033[33m'
    NABLA_UI_RED=$'\033[31m'
    NABLA_UI_BLUE=$'\033[36m'
    if [[ "${NABLA_UI_ASCII:-0}" != 1 && "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" == *UTF-8* ]]; then
      NABLA_UI_OK='✅' NABLA_UI_WARN='⚠️' NABLA_UI_FAIL='❌' NABLA_UI_INFO='ℹ️'
    fi
  fi
}
nabla_ui_status() {
  local level="${1:?level is required}"
  shift
  local symbol color
  case "${level}" in
    ok) symbol="${NABLA_UI_OK}"; color="${NABLA_UI_GREEN}" ;;
    warn) symbol="${NABLA_UI_WARN}"; color="${NABLA_UI_YELLOW}" ;;
    fail) symbol="${NABLA_UI_FAIL}"; color="${NABLA_UI_RED}" ;;
    info) symbol="${NABLA_UI_INFO}"; color="${NABLA_UI_BLUE}" ;;
    *) return 2 ;;
  esac
  printf '%s%s%s %s\n' "${color}" "${symbol}" "${NABLA_UI_RESET}" "$*"
}
