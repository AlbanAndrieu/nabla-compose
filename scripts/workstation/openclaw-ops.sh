#!/usr/bin/env bash
# shellcheck shell=bash
# Safe, content-free OpenClaw workstation triage. No service mutation or raw config output.
set -euo pipefail
# Add emoji/color only for interactive operator output; preserve machine-readable pipes.
if [[ -z "${OPENCLAW_STYLE_ACTIVE:-}" && -z "${NO_COLOR+x}" && "${OPENCLAW_COLOR:-auto}" != never && ( -t 1 || "${OPENCLAW_COLOR:-auto}" == always ) ]]; then
  export OPENCLAW_STYLE_ACTIVE=1
  bash "${BASH_SOURCE[0]}" "$@" | python3 "$(dirname -- "${BASH_SOURCE[0]}")/openclaw-terminal-style.py"
  exit "${PIPESTATUS[0]}"
fi
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
usage() {
  printf '%s\n' 'Usage: openclaw-ops.sh [--check|--cron|--skill-review|--heartbeat|--recent-errors|--memory|--auth|--routes|--backup-check|--smoke-model|--litellm-audit|--disable-irc]'
  printf '%s\n' 'Default --check is read-only. --smoke-model makes one billable request (24h cooldown). --disable-irc explicitly changes one config setting.'
}
mode="${1:---check}"
(($# <= 1)) || { usage >&2; exit 2; }
case "${mode}" in
  --check|--cron|--skill-review|--heartbeat|--recent-errors|--memory|--auth|--routes|--backup-check|--smoke-model|--litellm-audit|--disable-irc) ;;
  *) usage >&2; exit 2 ;;
esac
command -v openclaw >/dev/null 2>&1 || { echo 'ERROR: openclaw CLI missing' >&2; exit 2; }
diagnose_cron() {
  local id="7ed5dd9a-da30-479f-b0eb-4cc494fb4966"
  openclaw cron runs --id "${id}" --limit 50 |
    python3 "${ROOT}/scripts/workstation/openclaw-cron-runs-summary.py"
}
diagnose_skill_review() {
  local id="0363a286-4889-45b9-9a7b-aadf0285c42c"
  openclaw cron runs --id "${id}" --limit 20 |
    python3 "${ROOT}/scripts/workstation/openclaw-cron-runs-summary.py"
}
diagnose_heartbeat() {
  # A single recurring heartbeat can generate many historical task failures.
  # Summarize retained runs rather than echoing task text or credentials.
  local id="bb9757db-9559-4960-bb23-9b9770929ff1"
  openclaw cron runs --id "${id}" --limit 100 |
    python3 "${ROOT}/scripts/workstation/openclaw-cron-runs-summary.py"
}
diagnose_memory() {
  # Status is intentionally filtered: OpenClaw may include filesystem and provider metadata.
  openclaw memory status |
    grep -E '^(Memory Search|Provider:|Model:|Indexed:|Dirty:|Index identity:|Vector search:|Vector dims:|FTS:|Batch:)' || true
}
case "${mode}" in
  --check)
    echo '==> OpenClaw error counters (24h)'
    bash "${ROOT}/scripts/workstation/diagnose-openclaw-errors.sh" --since '24 hours ago'
    echo '==> Application file-log evidence (30m, redacted)'
    python3 "${ROOT}/scripts/workstation/openclaw-application-log-summary.py" 30
    echo '==> Cron run statistics'
    diagnose_cron
    echo '==> Main heartbeat runs (redacted)'
    diagnose_heartbeat
    echo '==> Failed main skill review (redacted)'
    diagnose_skill_review
    echo '==> Memory index summary'
    diagnose_memory
    echo '==> CLI authentication presence (redacted)'
    python3 "${ROOT}/scripts/workstation/openclaw-auth-presence.py"
    echo '==> OpenClaw dotenv credential syntax (redacted)'
    python3 "${ROOT}/scripts/workstation/openclaw-dotenv-diagnostic.py"
    echo '==> Provider route metadata (redacted)'
    python3 "${ROOT}/scripts/workstation/openclaw-route-metadata.py"
    echo '==> Backup prerequisite'
    bash "${ROOT}/scripts/workstation/backup-openclaw.sh" --check
    ;;
  --cron) diagnose_cron ;;
  --skill-review) diagnose_skill_review ;;
  --heartbeat) diagnose_heartbeat ;;
  --recent-errors) python3 "${ROOT}/scripts/workstation/openclaw-application-log-summary.py" 30 ;;
  --memory) diagnose_memory ;;
  --auth)
    python3 "${ROOT}/scripts/workstation/openclaw-auth-presence.py"
    python3 "${ROOT}/scripts/workstation/openclaw-dotenv-diagnostic.py"
    ;;
  --routes) python3 "${ROOT}/scripts/workstation/openclaw-route-metadata.py" ;;
  --backup-check) bash "${ROOT}/scripts/workstation/backup-openclaw.sh" --check ;;
  --litellm-audit) python3 "${ROOT}/scripts/workstation/openclaw-litellm-audit.py" ;;
  --smoke-model)
    # Explicitly billable: never run from --check, cron, or automatically.
    # Portable flock guards races; reserve cooldown BEFORE invoking OpenClaw.
    command -v flock >/dev/null 2>&1 || { echo 'ERROR: flock required for smoke cooldown' >&2; exit 2; }
    state_root="${XDG_STATE_HOME:-${HOME}/.local/state}/nabla-compose"
    mkdir -p -- "${state_root}"
    chmod 700 -- "${state_root}"
    marker="${state_root}/openclaw-main-smoke-last-attempt"
    exec 9>"${state_root}/openclaw-main-smoke.lock"
    flock -n 9 || { echo 'WARN: model smoke already running'; exit 3; }
    now="$(date +%s)"
    if [[ -f "${marker}" ]]; then
      previous="$(cat -- "${marker}")"
      if [[ "${previous}" =~ ^[0-9]+$ ]] && (( now < previous + 86400 )); then
        echo 'WARN: smoke not executed; one billable attempt per 24 hours'
        exit 3
      fi
    fi
    printf '%s\n' "${now}" > "${marker}"
    chmod 600 -- "${marker}"
    echo '==> One explicitly requested billable model smoke (24h cooldown)'
    # Fixed tiny prompt, deterministic daily session key, constrained execution.
    # Capture output and emit only success/failure; prevent model or tool data leaks.
    if output="$(openclaw agent --agent main \
      --session-key "nabla-main-smoke-$(date -u +%Y%m%d)" \
      --model litellm-main/gpt-4.1 --thinking off \
      --message 'Réponds uniquement OK.' --timeout 90 2>&1)"; then
      if printf '%s\n' "${output}" | grep -qx 'OK'; then
        echo 'OK model smoke: litellm-main/gpt-4.1 returned OK'
      else
        echo 'ERROR: model smoke returned unexpected response (raw output suppressed)' >&2
        exit 1
      fi
    else
      echo 'ERROR: model smoke failed (raw output suppressed)' >&2
      exit 1
    fi
    ;;
  --disable-irc)
    # Explicit opt-in; do not touch plugin allowlists, other channels or restart gateway.
    echo 'Setting channels.irc.enabled=false (explicit requested action)'
    openclaw config set channels.irc.enabled false
    echo 'Confirming IRC disabled:'
    value="$(openclaw config get channels.irc.enabled)"
    [[ "${value}" == false ]] || { echo 'ERROR: IRC state not confirmed false' >&2; exit 1; }
    echo 'OK: IRC disabled in config; Gateway may require a reviewed restart.'
    ;;
esac
