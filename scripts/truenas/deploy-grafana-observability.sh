#!/usr/bin/env bash
# TrueNAS App grafana-observability: the read-only Grafana MCP (mcpgrafana)
# behind the LiteLLM MCP gateway. check is read-only; apply creates or updates
# the Custom App from the canonical checkout, then re-runs check.
#
#   sudo bash scripts/truenas/deploy-grafana-observability.sh --check|--apply
#
# Its runtime secrets come first from the workstation:
#   scripts/litellm/mcp-gateway.sh apply   (materialize_runtime.py --ssh truenas)
set -euo pipefail

MODE="${1:---check}"
APP_ID=grafana-observability
CANONICAL_ROOT="${GRAFANA_OBSERVABILITY_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
SECRET_FILE="/mnt/cpool/secrets/runtime/${APP_ID}/.env.secrets"
MCP_URL="${GRAFANA_MCP_URL:-http://172.17.0.24:8014/mcp}"

# shellcheck source=../lib/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../lib/common.sh"

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: sudo bash $0 [--check|--apply]" ;;
esac
[[ "${EUID}" -eq 0 ]] || fail "run with sudo: TrueNAS middleware and the root-only runtime secret are needed"
for command in docker git jq midclt curl grep stat; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] || fail "run from the canonical checkout ${CANONICAL_ROOT}, not ${ROOT}"
cd "${CANONICAL_ROOT}"
# shellcheck source=../lib/truenas.sh
source "${CANONICAL_ROOT}/scripts/lib/truenas.sh"
truenas_repo_provenance "$(git rev-parse --show-toplevel)"

compose_path="${CANONICAL_ROOT}/apps/${APP_ID}/compose.yml"
docker compose -f "${compose_path}" config --quiet --no-interpolate --no-env-resolution

# Presence and shape only: never print a value.
secret=missing
if [[ -f "${SECRET_FILE}" && "$(stat -c '%U:%G %a' "${SECRET_FILE}")" == "root:root 600" ]] &&
  grep -q '^GRAFANA_SERVICE_ACCOUNT_TOKEN=.' "${SECRET_FILE}" &&
  grep -q '^MCP_GRAFANA_SERVER_TOKEN=.' "${SECRET_FILE}"; then
  secret=present
fi

if [[ "${MODE}" == --apply ]]; then
  [[ "${secret}" == present ]] || fail "${SECRET_FILE} is not ready: run scripts/litellm/mcp-gateway.sh apply first"
  truenas_reconcile_custom_app "${APP_ID}" "${compose_path}"
  truenas_wait_app_running "${APP_ID}" 300
fi

state="$(truenas_app_state "${APP_ID}")"
# The server must refuse a call without the gateway bearer token.
unauth="$(curl -sS --noproxy '*' -m 10 -o /dev/null -w '%{http_code}' -X POST \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' "${MCP_URL}" 2>/dev/null || true)"
status=DRIFT
if [[ "${state}" == RUNNING && "${secret}" == present && "${unauth}" == 401 ]]; then status=CONVERGED; fi
printf 'GRAFANA_OBSERVABILITY app=%s secret=%s unauthenticated=%s status=%s\n' "${state}" "${secret}" "${unauth:-none}" "${status}"
[[ "${status}" == CONVERGED ]]
