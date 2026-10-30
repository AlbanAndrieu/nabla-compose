#!/usr/bin/env bash
# Read-only multi-probe report; each probe executes even when another fails.
set -uo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "${ROOT}" || exit 2

failed=0
run_probe() {
    local label="$1"
    shift
    printf '\n--- %s ---\n' "${label}"
    if "$@"; then
        printf 'probe=%s result=completed\n' "${label}"
    else
        local rc=$?
        printf 'probe=%s result=failed exit=%s\n' "${label}" "${rc}"
        failed=$((failed + 1))
    fi
}

run_probe runtime python3 scripts/workstation/check-openclaw-runtime-alignment.py
run_probe model_cooldowns python3 scripts/workstation/diagnose-openclaw-model-cooldowns.py
run_probe rate_limit_evidence python3 scripts/workstation/observe-openclaw-rate-limits.py
# These two proxies must be distinguishable: local-only coverage is partial.
# Elevated remote log access is opt-in; never silently use sudo.
if [[ "${OPENCLAW_TRUENAS_LOG_SUDO:-0}" == "1" ]]; then
    run_probe litellm_dual_logs python3 scripts/workstation/diagnose-openclaw-litellm-dual-logs.py --truenas-sudo-logs
else
    run_probe litellm_dual_logs python3 scripts/workstation/diagnose-openclaw-litellm-dual-logs.py
fi
run_probe digest_cron python3 scripts/workstation/plan-openclaw-cron-recovery.py

printf '\nread_only=true model_requests=0 probe_failures=%s\n' "${failed}"
if (( failed > 0 )); then
    exit 2
fi
