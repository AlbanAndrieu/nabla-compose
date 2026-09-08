#!/usr/bin/env bash
set -euo pipefail

APP_ID="${WAZUH_TRUENAS_APP_ID:-wazuh}"
ROOT="$(git rev-parse --show-toplevel)"
COMPOSE_FILE="${WAZUH_COMPOSE_FILE:-${ROOT}/apps/wazuh/compose.yml}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] ||
  fail "run with sudo so Wazuh secrets and private keys remain root-owned"

for command in git jq midclt docker; do
  command -v "${command}" >/dev/null 2>&1 ||
    fail "${command} is required"
done

cd "${ROOT}"

printf '==> bootstrap Wazuh runtime secrets and TLS material\n'
bash scripts/truenas/bootstrap-wazuh.sh --apply

printf '==> verify Wazuh runtime prerequisites\n'
bash scripts/truenas/bootstrap-wazuh.sh --check

printf '==> update TrueNAS Wazuh Custom App\n'
midclt call -j app.update "${APP_ID}" "$(
  jq -cn     --arg include "${COMPOSE_FILE}"     '{
      custom_compose_config: {
        include: [$include]
      }
    }'
)"

printf '==> redeploy TrueNAS Wazuh Custom App\n'
midclt call -j app.redeploy "${APP_ID}"

printf '==> Wazuh TrueNAS state\n'
midclt call app.query   "[[\"id\",\"=\",\"${APP_ID}\"]]" |
  jq '.[0] | {id,state,active_workloads}'

printf 'OK: Wazuh bootstrap + update + redeploy completed\n'
