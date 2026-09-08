#!/usr/bin/env bash
set -euo pipefail

NETWORK="${FASTAPI_SAMPLE_OBSERVER_NETWORK:-sample-observer}"
MODE="${1:---check}"
ROLLBACK_TIMEOUT="${TRUENAS_UI_ROLLBACK_TIMEOUT_SECONDS:-60}"
RESTART_DELAY="${TRUENAS_UI_RESTART_DELAY_SECONDS:-1}"
ACTIVE_WAIT_ATTEMPTS="${TRUENAS_UI_ACTIVE_WAIT_ATTEMPTS:-30}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: sudo bash scripts/security/reconcile-truenas-observer-allowlist.sh [--check|--apply]" ;;
esac

for command in docker jq midclt python3 sleep seq; do
  command -v "${command}" >/dev/null 2>&1 ||
    fail "${command} is required"
done

observer_ip="$(
  docker network inspect "${NETWORK}" |
    jq -r '.[0].Labels["com.nabla.observer-ip"] // empty'
)"
[[ -n "${observer_ip}" ]] ||
  fail "${NETWORK} has no com.nabla.observer-ip label; prepare it first"

python3 - "${observer_ip}" <<'PY'
import ipaddress
import sys
ipaddress.ip_address(sys.argv[1])
PY

normalize_allowlist() {
  jq -c 'sort'
}

read_persisted_allowlist() {
  midclt call system.general.config |
    jq -c '.ui_allowlist // []' |
    normalize_allowlist
}

read_active_allowlist() {
  # TrueNAS intentionally keeps the API/UI source allowlist in memory until
  # the HTTP service is restarted. This private local middleware method exposes
  # that effective state without relying on the persisted database value.
  midclt call system.general.get_ui_allowlist |
    jq -c '. // []' |
    normalize_allowlist
}

current="$(read_persisted_allowlist)"
active="$(read_active_allowlist)"

desired="$(
  jq -cn     --argjson current "${current}"     --arg observer "${observer_ip}/32"     '
      (
        $current |
        map(
          select(
            . != "172.16.55.9/32" and
            . != "172.16.56.9/32"
          )
        )
      ) +
      [$observer] |
      unique |
      sort
    '
)"

printf 'Current persisted TrueNAS ui_allowlist:\n'
printf '%s\n' "${current}" | jq .
printf 'Current active TrueNAS ui_allowlist:\n'
printf '%s\n' "${active}" | jq .
printf 'Desired TrueNAS ui_allowlist:\n'
printf '%s\n' "${desired}" | jq .

if [[ "${current}" == "${desired}" && "${active}" == "${desired}" ]]; then
  printf 'OK: TrueNAS observer allowlist is persisted and active for %s\n' "${observer_ip}"
  exit 0
fi

if [[ "${MODE}" == "--check" ]]; then
  if [[ "${current}" != "${desired}" ]]; then
    printf 'PLAN: replace obsolete Sample observer /32 entries with %s/32 and restart the TrueNAS HTTP service\n' "${observer_ip}"
  else
    printf 'PLAN: persisted allowlist is correct but inactive; restart the TrueNAS HTTP service to activate it\n'
  fi
  exit 2
fi

[[ "${EUID}" -eq 0 ]] ||
  fail "--apply must run with sudo/root"

rollback_armed=false
if [[ "${current}" != "${desired}" ]]; then
  # TrueNAS does not apply UI/API settings until the HTTP service restarts.
  # Keep automatic rollback armed until the active in-memory allowlist is
  # observed after restart, then check in the change.
  midclt call system.general.update "$(
    jq -cn       --argjson allowlist "${desired}"       --argjson rollback_timeout "${ROLLBACK_TIMEOUT}"       --argjson ui_restart_delay "${RESTART_DELAY}"       '{
        ui_allowlist: $allowlist,
        rollback_timeout: $rollback_timeout,
        ui_restart_delay: $ui_restart_delay
      }'
  )" >/dev/null
  rollback_armed=true
else
  # Persisted state already matches, but the in-memory allowlist is stale.
  midclt call system.general.ui_restart "${RESTART_DELAY}" >/dev/null
fi

active_converged=false
for _attempt in $(seq 1 "${ACTIVE_WAIT_ATTEMPTS}"); do
  sleep 1
  if active="$(read_active_allowlist 2>/dev/null)" && [[ "${active}" == "${desired}" ]]; then
    active_converged=true
    break
  fi
done

if [[ "${active_converged}" != "true" ]]; then
  if [[ "${rollback_armed}" == "true" ]]; then
    fail "active ui_allowlist did not converge after HTTP restart; rollback remains armed and checkin was intentionally skipped"
  fi
  fail "active ui_allowlist did not converge after HTTP restart"
fi

persisted="$(read_persisted_allowlist)"
[[ "${persisted}" == "${desired}" ]] ||
  fail "persisted ui_allowlist does not match desired value after HTTP restart"

if [[ "${rollback_armed}" == "true" ]]; then
  midclt call system.general.checkin >/dev/null
fi

printf 'Active TrueNAS ui_allowlist after restart:\n'
printf '%s\n' "${active}" | jq .
printf 'OK: TrueNAS observer allowlist is persisted and active for %s/32\n' "${observer_ip}"
