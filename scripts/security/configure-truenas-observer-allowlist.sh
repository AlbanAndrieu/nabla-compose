#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${FASTAPI_SAMPLE_CONTAINER:-fastapi-sample}"
NETWORK="${FASTAPI_SAMPLE_OBSERVER_NETWORK:-intranet}"
EXPECTED_SOURCE_IP="${FASTAPI_SAMPLE_OBSERVER_IP:-172.16.55.9}"
ROLLBACK_TIMEOUT="${TRUENAS_UI_ROLLBACK_TIMEOUT:-300}"
UI_RESTART_DELAY="${TRUENAS_UI_RESTART_DELAY:-2}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

for command in docker jq midclt python3; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

if [[ "${ROLLBACK_TIMEOUT}" -lt 120 ]]; then
  fail "rollback timeout must be at least 120 seconds"
fi

container_ip="$(
  docker inspect "${CONTAINER}" |
    jq -r --arg network "${NETWORK}"       '.[0].NetworkSettings.Networks[$network].IPAddress // empty'
)"
[[ -n "${container_ip}" ]] ||
  fail "${CONTAINER} is not attached to Docker network ${NETWORK}"
[[ "${container_ip}" == "${EXPECTED_SOURCE_IP}" ]] ||
  fail "observer source IP drift: expected ${EXPECTED_SOURCE_IP}, got ${container_ip}"

observer_cidr="${container_ip}/32"

current="$(
  midclt call system.general.config |
    jq -c '.ui_allowlist // []'
)"
updated="$(
  jq -cn     --argjson current "${current}"     --arg cidr "${observer_cidr}"     '$current + [$cidr] | unique'
)"

if [[ "${current}" == "${updated}" ]]; then
  echo "OK: ${observer_cidr} is already present in persisted ui_allowlist"
else
  payload="$(
    jq -cn       --argjson allowlist "${updated}"       --argjson rollback "${ROLLBACK_TIMEOUT}"       --argjson restart "${UI_RESTART_DELAY}"       '{
        ui_allowlist: $allowlist,
        rollback_timeout: $rollback,
        ui_restart_delay: $restart
      }'
  )"

  echo "Applying narrow TrueNAS observer source allowlist entry: ${observer_cidr}"
  midclt call system.general.update "${payload}" >/dev/null
fi

sleep "$((UI_RESTART_DELAY + 3))"

persisted="$(midclt call system.general.config | jq -c '.ui_allowlist // []')"
active="$(midclt call system.general.get_ui_allowlist | jq -c '.')"

echo "Persisted ui_allowlist:"
printf '%s\n' "${persisted}" | jq .
echo "Active ui_allowlist:"
printf '%s\n' "${active}" | jq .

contains_cidr() {
  local json="$1"
  local cidr="$2"
  jq -e --arg cidr "${cidr}" 'index($cidr) != null' <<<"${json}" >/dev/null
}

contains_cidr "${persisted}" "${observer_cidr}" ||
  fail "${observer_cidr} is missing from persisted ui_allowlist"
contains_cidr "${active}" "${observer_cidr}" ||
  fail "${observer_cidr} is missing from active ui_allowlist"

if [[ "${current}" != "${updated}" ]]; then
  waiting="$(midclt call system.general.checkin_waiting)"
  [[ "${waiting}" != "null" ]] ||
    fail "no rollback timer is pending after system.general.update"
  printf 'Rollback timer remaining before validation: %s seconds\n' "${waiting}"
fi

echo "Validating authenticated TrueNAS observer calls before check-in"
docker exec -i "${CONTAINER}" /code/.venv/bin/python - <<'PY'
from nabla.integrations.truenas_client import build_truenas_adapter

adapter = build_truenas_adapter()
if adapter is None:
    raise SystemExit("TrueNAS adapter is not configured")

print("version:", adapter.system_version())
print("apps:", len(adapter.list_apps()))
PY

if [[ "${current}" != "${updated}" ]]; then
  waiting="$(midclt call system.general.checkin_waiting)"
  [[ "${waiting}" != "null" ]] ||
    fail "rollback timer expired before validation completed"

  echo "Observer validation succeeded; committing UI/API allowlist change"
  midclt call system.general.checkin >/dev/null

  waiting="$(midclt call system.general.checkin_waiting)"
  [[ "${waiting}" == "null" ]] ||
    fail "rollback timer is still pending after check-in"
fi

persisted="$(midclt call system.general.config | jq -c '.ui_allowlist // []')"
active="$(midclt call system.general.get_ui_allowlist | jq -c '.')"

contains_cidr "${persisted}" "${observer_cidr}" ||
  fail "${observer_cidr} disappeared from persisted ui_allowlist after check-in"
contains_cidr "${active}" "${observer_cidr}" ||
  fail "${observer_cidr} disappeared from active ui_allowlist after check-in"

echo "OK: TrueNAS observer ${observer_cidr} is active, persisted and validated"
