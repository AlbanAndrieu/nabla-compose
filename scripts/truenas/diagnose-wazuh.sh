#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
APP_ID="${WAZUH_APP_ID:-wazuh}"
CORE_CONTAINERS=(wazuh-indexer wazuh-manager wazuh-dashboard)

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check) ;;
  *)
    fail "usage: sudo bash scripts/truenas/diagnose-wazuh.sh --check"
    ;;
esac

[[ "${EUID}" -eq 0 ]] ||
  fail "run with sudo so Docker and TrueNAS runtime state are readable"

for command in docker midclt jq curl; do
  command -v "${command}" >/dev/null 2>&1 ||
    fail "${command} is required"
done

app_json="$(midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]")"
app_count="$(jq 'length' <<<"${app_json}")"
[[ "${app_count}" -eq 1 ]] ||
  fail "TrueNAS Custom App ${APP_ID} is missing"

app_state="$(jq -r '.[0].state // "UNKNOWN"' <<<"${app_json}")"
failures=0

for container in "${CORE_CONTAINERS[@]}"; do
  if ! docker inspect "${container}" >/dev/null 2>&1; then
    printf '❌ %s missing\n' "${container}" >&2
    failures=$((failures + 1))
    continue
  fi

  state="$(
    docker inspect "${container}"       --format '{{.State.Status}}'
  )"
  health="$(
    docker inspect "${container}"       --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}'
  )"
  printf '%s state=%s health=%s\n' "${container}" "${state}" "${health}"

  if [[ "${state}" != "running" ]]; then
    failures=$((failures + 1))
  fi
done

probe_https() {
  local label="$1"
  local url="$2"
  local accepted="$3"
  local code

  code="$(
    curl --insecure --silent --show-error       --output /dev/null       --write-out '%{http_code}'       --connect-timeout 3       --max-time 8       "${url}" 2>/dev/null || true
  )"

  if [[ ! "${code}" =~ ^(${accepted})$ ]]; then
    printf '❌ %s returned HTTP %s from %s\n'       "${label}" "${code:-000}" "${url}" >&2
    failures=$((failures + 1))
    return
  fi

  printf '%s=http_%s\n' "${label}" "${code}"
}

probe_https "indexer" "https://127.0.0.1:9202/" "200|401|403"
probe_https "manager_api" "https://127.0.0.1:55000/" "200|401|403|404"
probe_https "dashboard" "https://127.0.0.1:8444/" "200|302|401|403"

if docker inspect wazuh-forwarder >/dev/null 2>&1; then
  forwarder_state="$(
    docker inspect wazuh-forwarder --format '{{.State.Status}}'
  )"
  printf 'forwarder=%s (optional profile)\n' "${forwarder_state}"
else
  printf 'forwarder=disabled (optional profile)\n'
fi

[[ "${app_state}" == "RUNNING" ]] || {
  printf '❌ TrueNAS app state=%s\n' "${app_state}" >&2
  failures=$((failures + 1))
}

[[ "${failures}" -eq 0 ]] ||
  fail "Wazuh core acceptance failed with ${failures} issue(s)"

printf '✅ Wazuh core converged: TrueNAS=RUNNING manager/indexer/dashboard reachable\n'
