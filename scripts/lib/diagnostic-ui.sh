# shellcheck shell=bash
# Presentation helpers for read-only operator diagnostics. Never modify runtime.

DIAG_COLOR_ENABLED=0
DIAG_ICON_ENABLED=0
DIAG_WARNINGS=0
DIAG_FAILURES=0
DIAG_UNKNOWNS=0

diag_ui_init() {
  local color_mode="${1:-auto}"
  local icon_mode="${2:-auto}"
  DIAG_COLOR_ENABLED=0
  DIAG_ICON_ENABLED=0
  DIAG_WARNINGS=0
  DIAG_FAILURES=0
  DIAG_UNKNOWNS=0
  case "${color_mode}" in
    auto)
      if [[ -t 1 && "${TERM:-dumb}" != dumb && -z "${NO_COLOR:-}" ]]; then
        DIAG_COLOR_ENABLED=1
      fi
      ;;
    always)
      if [[ -z "${NO_COLOR:-}" ]]; then DIAG_COLOR_ENABLED=1; fi
      ;;
    never) ;;
    *) printf 'Invalid color mode: %s\n' "${color_mode}" >&2; return 2 ;;
  esac
  case "${icon_mode}" in
    auto)
      case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
        *UTF-8* | *utf8* | *utf-8*) DIAG_ICON_ENABLED=1 ;;
      esac
      ;;
    always) DIAG_ICON_ENABLED=1 ;;
    never) ;;
    *) printf 'Invalid icon mode: %s\n' "${icon_mode}" >&2; return 2 ;;
  esac
  return 0
}

diag_emit() {
  local level="$1" message="$2"
  local color='' icon='' reset=''
  case "${level}" in
    OK) color=$'\033[32m'; icon='✅' ;;
    WARN) color=$'\033[33m'; icon='⚠️' ;;
    FAIL) color=$'\033[31m'; icon='❌' ;;
    UNKNOWN) color=$'\033[35m'; icon='❔' ;;
    INFO) color=$'\033[36m'; icon='ℹ️' ;;
    *) printf 'Invalid diagnostic level\n' >&2; return 2 ;;
  esac
  if (( !DIAG_ICON_ENABLED )); then icon=''; fi
  if (( DIAG_COLOR_ENABLED )); then
    reset=$'\033[0m'
    if [[ -n "${icon}" ]]; then
      printf '%s%s %s: %s%s\n' "${color}" "${icon}" "${level}" "${message}" "${reset}"
    else
      printf '%s%s: %s%s\n' "${color}" "${level}" "${message}" "${reset}"
    fi
  else
    if [[ -n "${icon}" ]]; then
      printf '%s %s: %s\n' "${icon}" "${level}" "${message}"
    else
      printf '%s: %s\n' "${level}" "${message}"
    fi
  fi
}

diag_section() {
  local marker="$1" heading="$2" prefix='' icon=''
  [[ -n "${marker}" ]] && prefix="${marker} · "
  if (( DIAG_ICON_ENABLED )); then
    case "${marker}" in
      1/*) icon='🧭 ' ;;
      2/*) icon='🌐 ' ;;
      3/*) icon='🧩 ' ;;
      4/*) icon='🩺 ' ;;
      5/*) icon='📈 ' ;;
      6/*) icon='📊 ' ;;
      *) icon='🔎 ' ;;
    esac
  fi
  if (( DIAG_COLOR_ENABLED )); then
    printf '\n\033[1;36m== %s%s%s ==\033[0m\n' "${icon}" "${prefix}" "${heading}"
  else
    printf '\n== %s%s%s ==\n' "${icon}" "${prefix}" "${heading}"
  fi
}

diag_ok() { diag_emit OK "$*"; }
diag_info() { diag_emit INFO "$*"; }
diag_warn() { DIAG_WARNINGS=$((DIAG_WARNINGS + 1)); diag_emit WARN "$*"; }
diag_fail() { DIAG_FAILURES=$((DIAG_FAILURES + 1)); diag_emit FAIL "$*"; }
diag_unknown() { DIAG_UNKNOWNS=$((DIAG_UNKNOWNS + 1)); diag_emit UNKNOWN "$*"; }

diag_summary() {
  diag_section '' 'Diagnostic summary'
  printf 'checks: warnings=%d failures=%d unknown=%d\n' \
    "${DIAG_WARNINGS}" "${DIAG_FAILURES}" "${DIAG_UNKNOWNS}"
  if (( DIAG_FAILURES > 0 )); then
    diag_emit FAIL 'At least one required check failed'
  elif (( DIAG_WARNINGS > 0 || DIAG_UNKNOWNS > 0 )); then
    diag_emit WARN 'Further investigation or runtime acceptance needed'
  else
    diag_emit OK 'No observed diagnostic anomalies (not a security attestation)'
  fi
}
