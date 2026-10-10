#!/usr/bin/env bash
# shellcheck shell=bash
# Safe, content-free OpenClaw workstation triage. No service mutation or raw config output.
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
usage() {
  printf '%s\n' 'Usage: openclaw-ops.sh [--check|--cron|--memory|--backup-check|--disable-irc]'
  printf '%s\n' 'Default --check is read-only. --disable-irc explicitly changes one config setting.'
}
mode="${1:---check}"
(($# <= 1)) || { usage >&2; exit 2; }
case "${mode}" in
  --check|--cron|--memory|--backup-check|--disable-irc) ;;
  *) usage >&2; exit 2 ;;
esac
command -v openclaw >/dev/null 2>&1 || { echo 'ERROR: openclaw CLI missing' >&2; exit 2; }
diagnose_cron() {
  local id="7ed5dd9a-da30-479f-b0eb-4cc494fb4966"
  openclaw cron runs --id "${id}" --limit 50 |
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
    echo '==> Cron run statistics'
    diagnose_cron
    echo '==> Memory index summary'
    diagnose_memory
    echo '==> Backup prerequisite'
    bash "${ROOT}/scripts/workstation/backup-openclaw.sh" --check
    ;;
  --cron) diagnose_cron ;;
  --memory) diagnose_memory ;;
  --backup-check) bash "${ROOT}/scripts/workstation/backup-openclaw.sh" --check ;;
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
