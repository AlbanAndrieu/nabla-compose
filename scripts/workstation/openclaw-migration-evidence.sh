#!/usr/bin/env bash
# Read-only migration evidence sweep. Never mutate runtime, tokens or jobs.
set -uo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)" || exit 2
cd -- "${ROOT}" || exit 2
mode="${1:---diagnose}"
if (( $# > 1 )) || [[ "${mode}" != --tests && "${mode}" != --diagnose && "${mode}" != --inventory ]]; then
  printf 'Usage: %s [--tests|--diagnose|--inventory]\n' "$0" >&2
  exit 2
fi
# Stop on unknown hosts rather than claiming that an absent Workstation
# Gateway is DOWN on the TrueNAS appliance.
HOST="$(python3 scripts/workstation/openclaw-host-context.py --kind 2>/dev/null || :)"
case "${HOST}" in
  workstation|truenas) ;;
  *)
    printf '\033[1;33m⚠️  HÔTE INCONNU : diagnostics runtime bloqués.\033[0m\n' >&2
    printf 'Lancer sur la Workstation (OpenClaw) ou TrueNAS (LiteLLM).\n' >&2
    [[ "${mode}" == --tests ]] || exit 2
    ;;
esac
if [[ -t 1 && ! -v NO_COLOR ]]; then
  green=$'\033[1;32m'; yellow=$'\033[1;33m'
  blue=$'\033[1;36m'; reset=$'\033[0m'
else
  green=''; yellow=''; blue=''; reset=''
fi
printf '%b🖥️  Hôte : %s | diagnostic %s%b\n' "${blue}" "${HOST:-unknown}" "${mode}" "${reset}"
if [[ "${HOST}" == "truenas" && "${mode}" != "--tests" ]]; then
  printf '%b⚠️  TrueNAS détecté : les contrôles Gateway, sessions et digest Workstation seront ignorés.%b\n' "${yellow}" "${reset}"
fi
failed=0
passed=0
verbose="${OPENCLAW_DIAG_VERBOSE:-0}"
probe() {
  local name="$1" rc
  shift
  printf '\n%b🔎 %s%b\n' "${blue}" "${name}" "${reset}"
  local tmp
  tmp="$(mktemp)" || return 2
  if "$@" > "${tmp}" 2>&1; then rc=0; else rc=$?; fi
  if [[ "${verbose}" == "1" ]]; then
    cat "${tmp}"
  else
    # Only known fixed-field verdicts; never expose arbitrary logs, prompts,
    # bearer tokens, request paths, identities or raw JSON.
    grep -E '^(gateway_verdict=|cooldown_coverage=|truenas_tunnel=|models_allowlist=|provisioning=|database_status=|database_connectivity=|runtime_status=|openclaw_main_quota_state=|openclaw_cron_quota_state=|digest_top_argument=|cron_main_reference=|litellm_liveliness_http=|MIGRATION_EVIDENCE )' "${tmp}" | head -n 8 || :
    # Structured diagnostics: extract ONLY fixed-name, fixed-format statuses,
    # not entire JSON lines (which could contain other fields).
    grep -oE '"(coverage|access_reason|alignment|digest_state|digest_action|cron_main_reference|cron_main_action|gateway_verdict)"[[:space:]]*:[[:space:]]*"[A-Za-z0-9_]+"' "${tmp}" 2>/dev/null | sort -u | head -n 8 || :
  fi
  rm -f -- "${tmp}"
  if ((rc==0)); then
    printf '%b✅ PROBE %s completed%b\n' "${green}" "${name}" "${reset}"
    passed=$((passed+1))
  else
    printf '%b⚠️  PROBE %s unverified_or_failed exit=%s%b\n' "${yellow}" "${name}" "${rc}" "${reset}"
    failed=$((failed+1))
  fi
}
if [[ "${mode}" == --tests ]]; then
  probe focused_openclaw just openclaw-recovery-quality
  probe truenas_key_contracts just openclaw-truenas-model-keys-test
  probe truenas_virtual_key_contracts just openclaw-truenas-virtual-keys-test
  probe migration_inventory_contracts just openclaw-nabla-migration-test
  probe attribution_contracts just openclaw-429-attribution-test
  probe provenance_dispatch_contract python3 -m unittest discover -s tests -p test_truenas_litellm_secret_provenance_dispatch.py -v
elif [[ "${HOST}" == truenas ]]; then
  if [[ "${mode}" == --inventory ]]; then
    probe truenas_secret_provenance just openclaw-truenas-secret-provenance
    probe truenas_keys just openclaw-truenas-virtual-keys-status
  else
    probe truenas_litellm_status just openclaw-truenas-virtual-keys-status
    probe truenas_litellm_quota just openclaw-truenas-virtual-keys-quota
    probe workstation_upstream_auth just litellm-workstation-upstream-auth-check
    probe truenas_secret_provenance just openclaw-truenas-secret-provenance
  fi
elif [[ "${mode}" == --inventory ]]; then
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
  probe truenas_virtual_keys_quota just openclaw-truenas-virtual-keys-quota
  probe model_route_metadata python3 scripts/workstation/openclaw-route-metadata.py
  probe dual_litellm_logs just openclaw-litellm-dual-logs-check
  probe truenas_tunnel just openclaw-truenas-tunnel-check
  probe cron_parent just openclaw-cron-parent-check
  probe digest_top just openclaw-digest-top-check
  probe heartbeat_cron_runs bash scripts/workstation/openclaw-ops.sh --heartbeat
fi
printf '\n%b📋 MIGRATION_EVIDENCE host=%s mode=%s passed=%d unverified_or_failed=%d read_only=true model_requests=0%b\n' "${blue}" "${HOST:-unknown}" "${mode}" "${passed}" "${failed}" "${reset}"
(( failed == 0 )) || exit 2
