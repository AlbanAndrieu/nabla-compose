#!/usr/bin/env bash
set -euo pipefail

NETWORK="${FASTAPI_SAMPLE_OBSERVER_NETWORK:-sample-observer}"
MODE="${1:---check}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: sudo bash scripts/security/reconcile-truenas-observer-allowlist.sh [--check|--apply]" ;;
esac

for command in docker jq midclt python3; do
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

current="$(
  midclt call system.general.config |
    jq -c '.ui_allowlist // []'
)"

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
      unique
    '
)"

printf 'Current TrueNAS ui_allowlist:\n'
printf '%s\n' "${current}" | jq .
printf 'Desired TrueNAS ui_allowlist:\n'
printf '%s\n' "${desired}" | jq .

if [[ "${current}" == "${desired}" ]]; then
  printf 'OK: TrueNAS observer allowlist already reconciled for %s\n' "${observer_ip}"
  exit 0
fi

if [[ "${MODE}" == "--check" ]]; then
  printf 'PLAN: replace obsolete Sample observer /32 entries with %s/32\n' "${observer_ip}"
  exit 2
fi

[[ "${EUID}" -eq 0 ]] ||
  fail "--apply must run with sudo/root"

midclt call system.general.update "$(
  jq -cn     --argjson allowlist "${desired}"     '{ui_allowlist: $allowlist}'
)" >/dev/null

midclt call system.general.checkin >/dev/null

persisted="$(
  midclt call system.general.config |
    jq -c '.ui_allowlist // []'
)"

[[ "${persisted}" == "${desired}" ]] ||
  fail "persisted ui_allowlist does not match desired value after update/checkin"

printf 'OK: TrueNAS observer allowlist reconciled to %s/32\n' "${observer_ip}"
