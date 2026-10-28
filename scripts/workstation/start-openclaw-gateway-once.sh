#!/usr/bin/env bash
# One explicit Gateway start; no npm, SQLite repair or backup.
set -Eeuo pipefail
umask 077

if [[ "$#" != 1 || "${1:-}" != "--once" ]]; then
  echo "usage: $0 --once"
  exit 2
fi
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
UNIT="openclaw-gateway.service"
DB="${OPENCLAW_STATE_DIR:-${HOME}/.openclaw}/state/openclaw.sqlite"

if ! python3 "${HERE}/repair-openclaw-gateway-node.py" --select-installed-plan; then
  echo "gateway_start_once=blocked_wrong_installation"
  exit 2
fi

status="$(systemctl --user show "${UNIT}" --property=ActiveState --value)"
case "${status}" in
  failed|inactive) ;;
  active|activating)
    echo "gateway_start_once=skipped_already_running_or_starting"
    python3 "${HERE}/diagnose-openclaw-gateway-readiness.py" || true
    exit 2
    ;;
  *)
    echo "gateway_start_once=blocked_unexpected_state"
    exit 2
    ;;
esac
if ! command -v fuser >/dev/null; then
  echo "gateway_start_once=blocked_missing_sqlite_owner_probe"
  exit 2
fi
for file in "${DB}" "${DB}-wal" "${DB}-shm"; do
  if [[ -f "${file}" ]] && fuser -s "${file}" 2>/dev/null; then
    echo "gateway_start_once=blocked_sqlite_owned"
    exit 2
  fi
done
echo "gateway_start_once=attempted"
if ! systemctl --user start "${UNIT}" >/dev/null 2>&1; then
  python3 "${HERE}/diagnose-openclaw-gateway-service-failure.py" || true
  echo "gateway_start_once=start_command_failed"
  exit 2
fi
sleep 5
if ! systemctl --user is-active --quiet "${UNIT}"; then
  python3 "${HERE}/diagnose-openclaw-gateway-service-failure.py" || true
  echo "gateway_start_once=exited_after_start"
  exit 2
fi
if python3 "${HERE}/diagnose-openclaw-gateway-readiness.py"; then
  echo "gateway_start_once=healthy"
  echo "model_requests_sent=0"
  exit 0
fi
# Distinguish genuinely absent TCP listener from an HTTP-ready Gateway
# that only has pending startup, channel or browser UI admission.
python3 "${HERE}/diagnose-openclaw-gateway-listener.py" || true
echo "gateway_start_once=active_but_http_not_verified"
exit 2
