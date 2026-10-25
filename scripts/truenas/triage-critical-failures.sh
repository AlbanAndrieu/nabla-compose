#!/usr/bin/env bash
# Bounded read-only triage for the seven outstanding critical gates.
# Does NOT start Apps, redeploy, mutate secrets, or publish raw logs.
set -euo pipefail
umask 077

case "\${1:---check}" in
  --help|-h)
    printf '%s\n' 'Usage: sudo bash scripts/truenas/triage-critical-failures.sh --check'
    printf '%s\n' 'Runs seven read-only gates. Evidence is private on TrueNAS.'
    exit 0 ;;
  --check)
    (($# <= 1)) || { printf 'Unexpected arguments\n' >&2; exit 2; } ;;
  *)
    printf 'BLOCKED: read-only --check is the only supported action\n' >&2
    exit 2 ;;
esac

((EUID == 0)) || {
  printf 'BLOCKED: root required for protected TrueNAS metadata\n' >&2
  exit 2
}
for tool in mktemp chmod timeout python3; do
  command -v "$tool" >/dev/null 2>&1 || {
    printf 'BLOCKED: diagnostic prerequisite unavailable: %s\n' "$tool" >&2
    exit 2
  }
done

ROOT="$(cd -- "$(dirname -- "\${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$ROOT"
REPORT_ROOT="\${NABLA_MIGRATION_REPORT_ROOT:-/mnt/cpool/var/nabla/migration-20261024}"
[[ "$REPORT_ROOT" == /* && ! -L "$REPORT_ROOT" ]] || {
  printf 'BLOCKED: report root must be absolute and not symlinked\n' >&2
  exit 2
}
mkdir -p -- "$REPORT_ROOT"
[[ -d "$REPORT_ROOT" && ! -L "$REPORT_ROOT" ]] || exit 2
chmod 0700 -- "$REPORT_ROOT"
SESSION_DIR="$(mktemp -d "\${REPORT_ROOT}/focused-XXXXXX")"
chmod 0700 -- "$SESSION_DIR"
SUMMARY="\${SESSION_DIR}/summary.tsv"
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
  printf '%s=%s\n' "$gate" "$status"
}
run_gate() {
  local gate="$1" budget="$2" log status=0
  shift 2
  log="\${SESSION_DIR}/\${gate}.log"
  # Never echo command output or secret environment. All evidence stays 0600.
  timeout "$budget" "$@" >"$log" 2>&1 || status=$?
  chmod 0600 -- "$log"
  record_gate "$gate" "$status" "$log"
}

# This list matches the failed gate names in the operator's 25 October report.
# Each command is read-only. No service is restarted or reconfigured.
run_gate prometheus-targets 80 \
  bash scripts/truenas/diagnose-prometheus-targets.sh --check
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
run_gate akvorado-fresh-inserts 75 \
  python3 scripts/truenas/diagnose-akvorado-flow.py --strict --require-inserts --observe-seconds 30

printf 'Results: PASS=%d FAIL=%d UNVERIFIED=%d\n' "$passed" "$failed" "$unverified"
printf 'Private evidence: %s\n' "$SESSION_DIR"
printf 'Review: sudo cat %q\n' "$SUMMARY"
# Treat missing observations as incomplete acceptance, not successful service health.
((failed == 0 && unverified == 0))
