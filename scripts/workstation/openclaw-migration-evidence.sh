#!/usr/bin/env bash
# Read-only migration evidence sweep. Never mutate runtime, tokens or jobs.
set -uo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)" || exit 2
cd -- "$ROOT" || exit 2
mode="${1:---diagnose}"
if (( $# > 1 )) || [[ "$mode" != --tests && "$mode" != --diagnose && "$mode" != --inventory ]]; then
  printf 'Usage: %s [--tests|--diagnose|--inventory]\n' "$0" >&2
  exit 2
fi
failed=0
passed=0
probe() {
  local name="$1"; shift
  printf '\n=== %s ===\n' "$name"
  if "$@"; then
    printf 'PROBE %s completed\n' "$name"
    passed=$((passed+1))
  else
    local rc=$?
    printf 'PROBE %s unverified_or_failed exit=%s\n' "$name" "$rc"
    failed=$((failed+1))
  fi
}
if [[ "$mode" == --tests ]]; then
  probe focused_openclaw just openclaw-recovery-quality
  probe truenas_key_contracts just openclaw-truenas-model-keys-test
  probe truenas_virtual_key_contracts just openclaw-truenas-virtual-keys-test
  probe migration_inventory_contracts just openclaw-nabla-migration-test
  probe attribution_contracts just openclaw-429-attribution-test
elif [[ "$mode" == --inventory ]]; then
  probe legacy_inventory just openclaw-nabla-migration-check
  probe heartbeat_workspace python3 scripts/workstation/openclaw-heartbeat-workspace-audit.py
  probe gitops_heartbeat_briefing just openclaw-morning-briefing-check
  probe heartbeat_backup_metadata just openclaw-heartbeat-copies-check
  probe secret_provenance just openclaw-truenas-secret-provenance
else
  probe gateway_and_runtime just openclaw-gateway-readiness
  probe combined_diagnostics just openclaw-recovery-readonly
  probe 429_no_admin just openclaw-429-triage-no-admin
  probe truenas_routes_declared just openclaw-truenas-model-keys-check
  probe truenas_tunnel just openclaw-truenas-tunnel-check
  probe cron_parent just openclaw-cron-parent-check
  probe digest_top just openclaw-digest-top-check
  probe heartbeat_cron_runs bash scripts/workstation/openclaw-ops.sh --heartbeat
fi
printf '\nMIGRATION_EVIDENCE mode=%s passed=%d unverified_or_failed=%d read_only=true model_requests=0\n' "$mode" "$passed" "$failed"
(( failed == 0 )) || exit 2
