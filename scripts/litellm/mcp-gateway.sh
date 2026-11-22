#!/usr/bin/env bash
# LiteLLM MCP gateway as code (check, then apply).
#
# Vaultwarden is the source of truth for:
#   nabla/prod/homarr                 HOMARR_API_KEY (upstream key of the homarr server)
#   nabla/prod/grafana-observability  GRAFANA_SERVICE_ACCOUNT_TOKEN, MCP_GRAFANA_SERVER_TOKEN
#   nabla/prod/litellm-mcp-client     LITELLM_MCP_CLIENT_KEY (the one client key)
# apply:
#   - fills MCP_GRAFANA_SERVER_TOKEN and installs the mcp-grafana runtime file on
#     TrueNAS (materialize_runtime.py --ssh) for apps/mcp-grafana;
#   - upserts the homarr and grafana servers in the LiteLLM database through the
#     admin API: their credentials are encrypted there with LITELLM_SALT_KEY, so
#     LiteLLM needs no extra env file;
#   - mints the client virtual key: no LLM model, MCP access group nabla-mcp only,
#     also written to ~/.config/nabla/mcp/litellm-gateway.headers (600).
# No value is ever printed, and none reaches a command line.
#
# Usage (owner terminal: Vaultwarden unlocked, TrueNAS ControlMaster open):
#   scripts/litellm/mcp-gateway.sh check
#   scripts/litellm/mcp-gateway.sh apply
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
# Fixed TrueNAS endpoints. Never read the generic LITELLM_URL: the owner shell
# points it at the workstation LiteLLM, which shares the master key (22/11/2026).
LITELLM_URL=http://172.17.0.24:4000
HOMARR_MCP_URL=http://172.17.0.24:30100/api/mcp/mcp
GRAFANA_MCP_URL=http://172.17.0.24:8014/mcp
HOMARR_TOOLS="${ROOT}/scripts/litellm/homarr-readonly-tools.json"
SSH_HOST="${TRUENAS_SSH_HOST:-truenas}"
KEY_ALIAS=mcp-claude-code
ACCESS_GROUP=nabla-mcp
HEADERS_FILE="${MCP_KEY_DIR}/litellm-gateway.headers"
IMPORT=("python3" "${ROOT}/scripts/secrets/import_env_to_bitwarden.py" --manifest "${ROOT}/config/secrets/manifest.json")
MATERIALIZE=("python3" "${ROOT}/scripts/secrets/materialize_runtime.py" --app mcp-grafana --ssh "${SSH_HOST}")

die() {
  echo "❌ $*" >&2
  exit 1
}

[[ -n "${BW_SESSION:-}" ]] || die "unlock Vaultwarden in this terminal first (BW_SESSION is empty)"

field() { bw_field "$1" "$2" 2>/dev/null || true; }

# LiteLLM API (LAN only). The bearer key goes through a curl config on a file
# descriptor and the JSON body through stdin: neither is ever in an argv.
api() { # KEY METHOD PATH [JSON]; sets API_CODE and API_BODY
  local out data=()
  [[ $# -lt 4 ]] || data=(--data-binary @-)
  out="$(printf '%s' "${4:-}" |
    curl -sS --noproxy '*' -K <(printf 'header = "Authorization: Bearer %s"\n' "$1") -X "$2" \
      -H 'Content-Type: application/json' "${data[@]}" \
      -w '\n%{http_code}' "${LITELLM_URL}$3")" || die "curl $2 $3 failed (exit $?)"
  API_CODE="${out##*$'\n'}"
  API_BODY="${out%$'\n'*}"
}

# Desired server rows; the upstream secret comes from UPSTREAM_KEY in the
# environment of jq, never from its argv.
server_payload() { # homarr|grafana
  case "$1" in
    homarr)
      jq -nc --slurpfile tools "${HOMARR_TOOLS}" --arg url "${HOMARR_MCP_URL}" --arg group "${ACCESS_GROUP}" '{
        server_id: "homarr", server_name: "homarr", alias: "homarr", transport: "http", url: $url,
        description: "Homarr dashboard, read-only tools",
        auth_type: "api_key", credentials: {auth_value: $ENV.UPSTREAM_KEY, upstream_token_header: "ApiKey"},
        mcp_access_groups: [$group], allowed_tools: $tools[0]}'
      ;;
    grafana)
      jq -nc --arg url "${GRAFANA_MCP_URL}" --arg group "${ACCESS_GROUP}" '{
        server_id: "grafana", server_name: "grafana", alias: "grafana", transport: "http", url: $url,
        description: "Grafana dashboards, Prometheus, Loki and alerts (read-only Viewer)",
        auth_type: "bearer_token", credentials: {auth_value: $ENV.UPSTREAM_KEY},
        mcp_access_groups: [$group]}'
      ;;
  esac
}

read_state() {
  SA_TOKEN="$(field nabla/prod/grafana-observability GRAFANA_SERVICE_ACCOUNT_TOKEN)"
  SERVER_TOKEN="$(field nabla/prod/grafana-observability MCP_GRAFANA_SERVER_TOKEN)"
  HOMARR_KEY="$(field nabla/prod/homarr HOMARR_API_KEY)"
  CLIENT_KEY="$(field nabla/prod/litellm-mcp-client LITELLM_MCP_CLIENT_KEY)"
  MASTER_KEY="$(field nabla/prod/litellm LITELLM_MASTER_KEY)"
  [[ -n "${MASTER_KEY}" ]] || die "nabla/prod/litellm has no LITELLM_MASTER_KEY"
  VAULT=ok
  if [[ -z "${SA_TOKEN}" || -z "${SERVER_TOKEN}" || -z "${HOMARR_KEY}" ]]; then VAULT=drift; fi
  RUNTIME=ok
  if ! "${MATERIALIZE[@]}" --verify >/dev/null 2>&1; then RUNTIME=drift; fi
  # Credentials come back redacted: compare the non-secret shape only.
  SERVERS=drift
  api "${MASTER_KEY}" GET /v1/mcp/server
  if [[ "${API_CODE}" == 200 ]] && jq -e --arg g "${ACCESS_GROUP}" --arg h "${HOMARR_MCP_URL}" --arg u "${GRAFANA_MCP_URL}" \
    --slurpfile tools "${HOMARR_TOOLS}" '
      (map(select(.server_id == "homarr" and .url == $h and .auth_type == "api_key"
        and .mcp_access_groups == [$g] and ((.allowed_tools // []) | sort) == ($tools[0] | sort))) | length == 1)
      and (map(select(.server_id == "grafana" and .url == $u and .auth_type == "bearer_token"
        and .mcp_access_groups == [$g])) | length == 1)' <<<"${API_BODY}" >/dev/null 2>&1; then
    SERVERS=ok
  fi
  CLIENT=absent
  if [[ -n "${CLIENT_KEY}" ]]; then
    api "${CLIENT_KEY}" GET /key/info
    if [[ "${API_CODE}" == 200 ]]; then CLIENT=valid; else CLIENT=invalid; fi
  fi
  HEADERS=absent
  if [[ -e "${HEADERS_FILE}" ]]; then
    HEADERS=bad-mode
    if mcp_private_file litellm-gateway.headers litellm >/dev/null 2>&1; then HEADERS=present; fi
  fi
}

report() {
  local status=DRIFT
  if [[ "${VAULT}" == ok && "${RUNTIME}" == ok && "${SERVERS}" == ok && "${CLIENT}" == valid && "${HEADERS}" == present ]]; then
    status=CONVERGED
  fi
  echo "MCP_GATEWAY vaultwarden=${VAULT} runtime=${RUNTIME} servers=${SERVERS} client_key=${CLIENT} headers_file=${HEADERS} status=${status}"
  [[ "${status}" == CONVERGED ]]
}

read_state
if [[ "${MODE}" == check ]]; then
  report || exit 3
  exit 0
fi

[[ -n "${SA_TOKEN}" ]] || die "no Grafana MCP token yet: run scripts/grafana/mcp-identity.sh apply first"
[[ -n "${HOMARR_KEY}" ]] || die "nabla/prod/homarr has no HOMARR_API_KEY"
if [[ -z "${SERVER_TOKEN}" ]]; then
  SERVER_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  GRAFANA_SERVICE_ACCOUNT_TOKEN="${SA_TOKEN}" MCP_GRAFANA_SERVER_TOKEN="${SERVER_TOKEN}" \
    "${IMPORT[@]}" --app mcp-grafana --apply --update-existing
fi
"${MATERIALIZE[@]}" --install

# Upsert on every apply: credentials cannot be read back, so always resend them.
for server in homarr grafana; do
  if [[ "${server}" == homarr ]]; then upstream="${HOMARR_KEY}"; else upstream="${SERVER_TOKEN}"; fi
  payload="$(UPSTREAM_KEY="${upstream}" server_payload "${server}")"
  api "${MASTER_KEY}" GET "/v1/mcp/server/${server}"
  if [[ "${API_CODE}" == 200 ]]; then method=PUT; else method=POST; fi
  api "${MASTER_KEY}" "${method}" /v1/mcp/server "${payload}"
  [[ "${API_CODE}" == 200 || "${API_CODE}" == 201 ]] || die "${method} MCP server ${server} failed (HTTP ${API_CODE})"
  echo "✅ MCP server ${server} (${method})"
done
unset upstream payload

if [[ "${CLIENT}" != valid || "${HEADERS}" != present ]]; then
  # A key is shown only at creation: replace any key left under this alias.
  api "${MASTER_KEY}" POST /key/delete "{\"key_aliases\":[\"${KEY_ALIAS}\"]}"
  api "${MASTER_KEY}" POST /key/generate "$(jq -cn --arg a "${KEY_ALIAS}" --arg g "${ACCESS_GROUP}" '{key_alias:$a,
    models:["no-default-models"], object_permission:{mcp_access_groups:[$g]},
    metadata:{purpose:"MCP gateway client (Claude Code, Cursor)"}}')"
  [[ "${API_CODE}" == 200 ]] || die "key generation failed (HTTP ${API_CODE})"
  CLIENT_KEY="$(jq -er '.key' <<<"${API_BODY}")" || die "key generation returned no key"
  LITELLM_MCP_CLIENT_KEY="${CLIENT_KEY}" "${IMPORT[@]}" --app litellm-mcp-client --apply --update-existing
  install -d -m 700 "${MCP_KEY_DIR}"
  tmp="$(mktemp "${HEADERS_FILE}.XXXXXX")"
  trap 'rm -f "${tmp}"' EXIT
  printf 'x-litellm-api-key: Bearer %s\n' "${CLIENT_KEY}" >"${tmp}"
  chmod 600 "${tmp}"
  mv -f "${tmp}" "${HEADERS_FILE}"
  trap - EXIT
  echo "✅ client key ${KEY_ALIAS} in ${HEADERS_FILE} (600) and nabla/prod/litellm-mcp-client"
fi

read_state
report
