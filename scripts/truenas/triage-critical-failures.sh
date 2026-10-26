#!/usr/bin/env bash
# Bounded read-only triage for the seven outstanding critical gates.
# Does NOT start Apps, redeploy, mutate secrets, or publish raw logs.
set -euo pipefail
umask 077

COLOR_MODE=auto
ICON_MODE=auto
ACTION_FLAGS=0
VERBOSE=false
REMAINING=false
while (($#)); do
  case "$1" in
    -h|--help)
      printf '%s\n' 'Usage: sudo bash scripts/truenas/triage-critical-failures.sh --check [--color auto|always|never] [--icons auto|always|never] [--remaining] [--verbose]'
      printf '%s\n' 'Runs seven read-only gates. Evidence stays private on TrueNAS.'
      exit 0 ;;
    --check) ACTION_FLAGS=$((ACTION_FLAGS + 1)); shift ;;
    --color)
      (($# >= 2)) || exit 2
      COLOR_MODE="$2"; shift 2 ;;
    --color=*) COLOR_MODE="${1#*=}"; shift ;;
    --icons)
      (($# >= 2)) || exit 2
      ICON_MODE="$2"; shift 2 ;;
    --icons=*) ICON_MODE="${1#*=}"; shift ;;
    --no-color) COLOR_MODE=never; shift ;;
    --no-icons) ICON_MODE=never; shift ;;
    --verbose) VERBOSE=true; shift ;;
    --remaining) REMAINING=true; shift ;;
    *)
      printf 'BLOCKED: unknown or mutating triage argument (see --help)\n' >&2
      exit 2 ;;
  esac
done
((ACTION_FLAGS <= 1)) || {
  printf 'BLOCKED: --check may only be specified once\n' >&2
  exit 2
}

((EUID == 0)) || {
  printf 'BLOCKED: root required for protected TrueNAS metadata\n' >&2
  exit 2
}
for tool in mktemp chmod timeout python3 stat readlink; do
  command -v "$tool" >/dev/null 2>&1 || {
    printf 'BLOCKED: diagnostic prerequisite unavailable: %s\n' "$tool" >&2
    exit 2
  }
done

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$ROOT"
UI_LIB="${ROOT}/scripts/lib/diagnostic-ui.sh"
[[ -f "$UI_LIB" && ! -L "$UI_LIB" ]] || {
  printf 'BLOCKED: diagnostic UI library unavailable or symlinked\n' >&2
  exit 2
}
# shellcheck source=../lib/diagnostic-ui.sh
source "$UI_LIB"
diag_ui_init "$COLOR_MODE" "$ICON_MODE" || exit 2
EXPECTED_ROOT="/mnt/cpool/var/nabla/migration-20261024"
REPORT_ROOT="${NABLA_MIGRATION_REPORT_ROOT:-$EXPECTED_ROOT}"
# Fail closed; never chmod unrelated directories, even as root.
[[ "$REPORT_ROOT" == "$EXPECTED_ROOT" &&
   -d "$REPORT_ROOT" && ! -L "$REPORT_ROOT" &&
   "$(readlink -f -- "$REPORT_ROOT")" == "$EXPECTED_ROOT" &&
   "$(stat -c '%a' -- "$REPORT_ROOT")" == 700 ]] || {
  printf 'BLOCKED: private report root must be reviewed 0700 path\n' >&2
  exit 2
}
SESSION_DIR="$(mktemp -d "${REPORT_ROOT}/focused-XXXXXX")"
chmod 0700 -- "$SESSION_DIR"
SUMMARY="${SESSION_DIR}/summary.tsv"
printf 'gate\tstatus\texit_code\tprivate_log\n' >"$SUMMARY"
chmod 0600 -- "$SUMMARY"

passed=0
failed=0
unverified=0
record_gate() {
  local gate="$1" code="$2" log="$3" status
  case "$code" in
    0) status=PASS; passed=$((passed+1)) ;;
    2|124) status=UNVERIFIED; unverified=$((unverified+1)) ;;
    *) status=FAIL; failed=$((failed+1)) ;;
  esac
  printf '%s\t%s\t%s\t%s\n' "$gate" "$status" "$code" "$log" >>"$SUMMARY"
  case "$status" in
    PASS) diag_ok "$gate" ;;
    FAIL) diag_fail "$gate (see private report)" ;;
    UNVERIFIED) diag_unknown "$gate (no conclusive evidence)" ;;
  esac
  if [[ "$VERBOSE" == true && "$status" != PASS ]]; then
    diag_info "evidence: $log"
  fi
}
run_gate() {
  local gate="$1" budget="$2" log status=0
  shift 2
  log="${SESSION_DIR}/${gate}.log"
  # Never echo command output or secret environment. All evidence stays 0600.
  timeout "$budget" "$@" >"$log" 2>&1 || status=$?
  chmod 0600 -- "$log"
  record_gate "$gate" "$status" "$log"
}

# This list matches the failed gate names in the operator's 25 October report.
# Each command is read-only. No service is restarted or reconfigured.
run_gate prometheus-targets 80 \
  bash scripts/truenas/diagnose-prometheus-targets.sh --check
if [[ "$REMAINING" != true ]]; then
run_gate prometheus-config-access 30 \
  bash scripts/truenas/repair-prometheus-config-access.sh --check
run_gate openrag-startup 65 \
  bash scripts/truenas/diagnose-openrag-startup.sh --check
run_gate ai-runtime-recovery 85 \
  python3 scripts/truenas/diagnose-ai-secret-recovery.py --check --strict --scope openrag
run_gate openrag-opensearch-legacy-secret 30 \
  bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
run_gate openrag-backstage-bundle 30 \
  python3 scripts/check-service-migration-bundle.py --app openrag
fi
run_gate akvorado-fresh-inserts 75 \
  python3 scripts/truenas/diagnose-akvorado-flow.py --strict --require-inserts --observe-seconds 30

if [[ "$REMAINING" == true ]]; then
  diag_section '' 'Remaining Prometheus and Akvorado gates'
else
  diag_section '' 'Seven-gate critical migration summary'
fi
printf 'Results: PASS=%d FAIL=%d UNVERIFIED=%d\n' "$passed" "$failed" "$unverified"
diag_info "Private evidence: $SESSION_DIR"
printf 'Review: sudo cat %q\n' "$SUMMARY"
# Treat missing observations as incomplete acceptance, not successful service health.
((failed == 0 && unverified == 0))
