#!/usr/bin/env bash
# Read-only Grafana identity for the Grafana MCP (check, then apply).
#
# Vaultwarden holds both secrets: the admin password (nabla/prod/grafana,
# GRAFANA_ADMIN_PASSWORD) and the MCP token (nabla/prod/grafana-observability,
# GRAFANA_SERVICE_ACCOUNT_TOKEN). apply:
#   1. generates the admin password when Vaultwarden has none, stores it, then
#      sets it in Grafana (grafana cli on TrueNAS, password on stdin). The
#      runtime GRAFANA_ADMIN_PASSWORD only seeds a new database;
#   2. creates the Viewer service account mcp-readonly with OpenTofu
#      (infrastructure/grafana);
#   3. mints one token straight into Vaultwarden; scripts/litellm/mcp-gateway.sh
#      installs it for the mcp-grafana App on TrueNAS.
# No value is ever printed, and none reaches a command line.
#
# Usage (owner terminal: Vaultwarden unlocked, TrueNAS ControlMaster open):
#   scripts/grafana/mcp-identity.sh check
#   scripts/grafana/mcp-identity.sh apply
set -euo pipefail

MODE="${1:-}"
case "${MODE}" in
  check | apply) ;;
  *)
    echo "usage: $0 check|apply" >&2
    exit 2
    ;;
esac

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=scripts/mcp/lib.sh
source "${ROOT}/scripts/mcp/lib.sh"
# Fixed TrueNAS Grafana: an inherited GRAFANA_URL must not redirect the admin credential.
export GRAFANA_URL=http://172.17.0.24:30037
SSH_HOST="${TRUENAS_SSH_HOST:-truenas}"
CONTAINER=grafana-stack
SA_NAME=mcp-readonly
IMPORT=("python3" "${ROOT}/scripts/secrets/import_env_to_bitwarden.py" --manifest "${ROOT}/config/secrets/manifest.json")

die() {
  echo "❌ $*" >&2
  exit 1
}

[[ -n "${BW_SESSION:-}" ]] || die "unlock Vaultwarden in this terminal first (BW_SESSION is empty)"

# Grafana API as admin. The credentials reach curl through its stdin config.
api() { # METHOD PATH [JSON]; sets API_CODE and API_BODY
  local out data=()
  [[ $# -lt 3 ]] || data=(-d "$3")
  # LAN only: an operator shell proxy must not see the admin credentials.
  out="$(printf 'user = "admin:%s"\n' "${ADMIN_PW}" |
    curl -sS --noproxy '*' -K - -X "$1" -H 'Content-Type: application/json' "${data[@]}" \
      -w '\n%{http_code}' "${GRAFANA_URL}$2")" || die "curl $1 $2 failed (exit $?)"
  API_CODE="${out##*$'\n'}"
  API_BODY="${out%$'\n'*}"
}

read_state() {
  ADMIN_PW="$(bw_field nabla/prod/grafana GRAFANA_ADMIN_PASSWORD 2>/dev/null)" || ADMIN_PW=""
  [[ "${ADMIN_PW}" != *[\"\\]* ]] || die "GRAFANA_ADMIN_PASSWORD holds a quote or backslash; regenerate it"
  ADMIN=absent SA_ID="" SA_ROLE="" TOKENS=0
  if [[ -n "${ADMIN_PW}" ]]; then
    api GET /api/user
    if [[ "${API_CODE}" == 200 ]]; then ADMIN=ok; else ADMIN=denied; fi
  fi
  if [[ "${ADMIN}" == ok ]]; then
    api GET "/api/serviceaccounts/search?query=${SA_NAME}"
    SA_ID="$(jq -r --arg n "${SA_NAME}" '[.serviceAccounts[] | select(.name == $n)][0].id // empty' <<<"${API_BODY}")"
    SA_ROLE="$(jq -r --arg n "${SA_NAME}" '[.serviceAccounts[] | select(.name == $n)][0].role // empty' <<<"${API_BODY}")"
    if [[ -n "${SA_ID}" ]]; then
      api GET "/api/serviceaccounts/${SA_ID}/tokens"
      TOKENS="$(jq 'length' <<<"${API_BODY}")"
    fi
  fi
  VAULT=absent
  if bw_field nabla/prod/grafana-observability GRAFANA_SERVICE_ACCOUNT_TOKEN >/dev/null 2>&1; then VAULT=present; fi
}

report() {
  local status=DRIFT sa=absent
  [[ -z "${SA_ID}" ]] || sa="present(${SA_ROLE})"
  if [[ "${ADMIN}" == ok && "${SA_ROLE}" == Viewer && "${TOKENS}" == 1 && "${VAULT}" == present ]]; then
    status=CONVERGED
  fi
  echo "MCP_GRAFANA admin=${ADMIN} service_account=${sa} tokens=${TOKENS} vaultwarden_token=${VAULT} status=${status}"
  [[ "${status}" == CONVERGED ]]
}

read_state
if [[ "${MODE}" == check ]]; then
  report || exit 3
  exit 0
fi

if [[ "${ADMIN}" == absent ]]; then
  # Store first: a password set in Grafana but lost would lock the admin out.
  ADMIN_PW="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  GRAFANA_LLM_API_KEY="$(bw_field nabla/prod/grafana GRAFANA_LLM_API_KEY)" GRAFANA_ADMIN_PASSWORD="${ADMIN_PW}" \
    "${IMPORT[@]}" --app grafana --apply --update-existing
  ADMIN=denied
fi
if [[ "${ADMIN}" == denied ]]; then
  printf '%s\n' "${ADMIN_PW}" |
    ssh -o BatchMode=yes "${SSH_HOST}" "sudo -n docker exec -i ${CONTAINER} grafana cli admin reset-admin-password --password-from-stdin" >/dev/null
  api GET /api/user
  [[ "${API_CODE}" == 200 ]] || die "Grafana still refuses the Vaultwarden admin password (HTTP ${API_CODE})"
  echo "✅ Grafana admin password = Vaultwarden nabla/prod/grafana"
fi

read_state
if [[ -z "${SA_ID}" || "${SA_ROLE}" != Viewer ]]; then
  # Grafana and the Garage state backend (s3.int) are LAN-only: bypass any shell proxy.
  grafana_host="${GRAFANA_URL#*://}"
  lan="${grafana_host%%[:/]*},.int.albandrieu.com"
  GRAFANA_AUTH="admin:${ADMIN_PW}" NO_PROXY="${lan},${NO_PROXY:-}" no_proxy="${lan},${no_proxy:-}" \
    bash "${ROOT}/scripts/infra/terragrunt-safe.sh" infrastructure/grafana apply -auto-approve
  read_state
  [[ -n "${SA_ID}" ]] || die "service account ${SA_NAME} still absent after the OpenTofu apply"
fi

if [[ "${TOKENS}" != 1 || "${VAULT}" != present ]]; then
  # A token is shown only at creation: without the Vaultwarden copy, rotate it.
  api GET "/api/serviceaccounts/${SA_ID}/tokens"
  for id in $(jq -r '.[].id' <<<"${API_BODY}"); do
    api DELETE "/api/serviceaccounts/${SA_ID}/tokens/${id}"
  done
  api POST "/api/serviceaccounts/${SA_ID}/tokens" '{"name":"mcp"}'
  [[ "${API_CODE}" == 200 ]] || die "token creation failed (HTTP ${API_CODE})"
  token="$(jq -er '.key' <<<"${API_BODY}")" || die "token creation returned no key"
  # The gateway bearer token shares the item: keep it.
  server_token="$(bw_field nabla/prod/grafana-observability MCP_GRAFANA_SERVER_TOKEN 2>/dev/null)" || server_token=""
  GRAFANA_SERVICE_ACCOUNT_TOKEN="${token}" MCP_GRAFANA_SERVER_TOKEN="${server_token}" \
    "${IMPORT[@]}" --app mcp-grafana --apply --update-existing
  unset token server_token
  echo "✅ token ${SA_NAME}/mcp in nabla/prod/grafana-observability"
fi

read_state
report
