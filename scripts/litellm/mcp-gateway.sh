#!/usr/bin/env bash
# LiteLLM MCP gateway as code (check, then apply).
#
# Vaultwarden is the source of truth; config/secrets/manifest.json maps each item to
# the runtime file of its TrueNAS App. This script owns:
#   - the generated tokens of GENERATED (bearer tokens the gateway presents to the
#     MCP sidecars, GATUS_EXTERNAL_TOKEN) and the runtime files of RUNTIME_APPS,
#     installed on TrueNAS with materialize_runtime.py --ssh;
#   - the credentialed servers of DB_SERVERS, upserted in the LiteLLM database
#     through the admin API: credentials are encrypted there with LITELLM_SALT_KEY.
#     Servers without a credential live in apps/litellm/config.yaml;
#   - the client virtual key (nabla/prod/litellm-mcp-client): no LLM model, MCP
#     access group nabla-mcp only, also in ~/.config/nabla/mcp/litellm-gateway.headers (600).
# Upstream identities come first: scripts/grafana/mcp-identity.sh apply and
# scripts/defectdojo/mcp-identity.sh apply (Sentry reuses SENTRY_ACCESS_TOKEN).
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
# Fixed TrueNAS endpoint. Never read the generic LITELLM_URL: the owner shell
# points it at the workstation LiteLLM, which shares the master key (22/11/2026).
LITELLM_URL=http://172.17.0.24:4000
SSH_HOST="${TRUENAS_SSH_HOST:-truenas}"
KEY_ALIAS=mcp-claude-code
ACCESS_GROUP=nabla-mcp
HEADERS_FILE="${MCP_KEY_DIR}/litellm-gateway.headers"
MANIFEST="${ROOT}/config/secrets/manifest.json"
IMPORT=("python3" "${ROOT}/scripts/secrets/import_env_to_bitwarden.py" --manifest "${MANIFEST}")
MATERIALIZE=("python3" "${ROOT}/scripts/secrets/materialize_runtime.py" --ssh "${SSH_HOST}")

# app|field: generated when Vaultwarden lacks it.
GENERATED=(
  "mcp-grafana|MCP_GRAFANA_SERVER_TOKEN"
  "gatus|GATUS_EXTERNAL_TOKEN"
  "mcp-sentry|MCP_SENTRY_SERVER_TOKEN"
  "mcp-defectdojo|MCP_DEFECTDOJO_SERVER_TOKEN"
)
RUNTIME_APPS=(mcp-grafana gatus mcp-gatus mcp-sentry mcp-defectdojo)
# name|url|auth[:header]|item|field|allowed tools file|description
DB_SERVERS=(
  "homarr|http://172.17.0.24:30100/api/mcp/mcp|api_key:ApiKey|nabla/prod/homarr|HOMARR_API_KEY|homarr-readonly-tools.json|Homarr dashboard, read-only tools"
  "grafana|http://172.17.0.24:8014/mcp|bearer_token|nabla/prod/grafana-observability|MCP_GRAFANA_SERVER_TOKEN||Grafana dashboards, Prometheus, Loki and alerts (read-only Viewer)"
  "sentry|http://172.17.0.24:8016/mcp|bearer_token|nabla/prod/sentry|MCP_SENTRY_SERVER_TOKEN||Self-hosted Sentry issues, events and traces (inspect skills only)"
  "defectdojo|http://172.17.0.24:8017/mcp|bearer_token|nabla/prod/mcp-defectdojo|MCP_DEFECTDOJO_SERVER_TOKEN|defectdojo-readonly-tools.json|DefectDojo findings, products and engagements (read-only user and tools)"
)

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

# Desired server row; the upstream secret comes from UPSTREAM_KEY in the
# environment of jq, never from its argv.
server_payload() { # NAME URL AUTH[:HEADER] TOOLS_FILE DESCRIPTION
  local tools=null
  [[ -z "$4" ]] || tools="$(<"${ROOT}/scripts/litellm/$4")"
  jq -nc --arg n "$1" --arg url "$2" --arg auth "${3%%:*}" --arg header "${3#*:}" --arg d "$5" \
    --arg group "${ACCESS_GROUP}" --argjson tools "${tools}" '{
      server_id: $n, server_name: $n, alias: $n, transport: "http", url: $url, description: $d,
      auth_type: $auth, credentials: ({auth_value: $ENV.UPSTREAM_KEY}
        + if $auth == "api_key" then {upstream_token_header: $header} else {} end),
      mcp_access_groups: [$group]} + if $tools == null then {} else {allowed_tools: $tools} end'
}

desired_shapes() {
  local row name url auth tools desc
  for row in "${DB_SERVERS[@]}"; do
    IFS='|' read -r name url auth _ _ tools desc <<<"${row}"
    UPSTREAM_KEY='' server_payload "${name}" "${url}" "${auth}" "${tools}" "${desc}"
  done | jq -sc .
}

# Generate FIELD of APP's item when Vaultwarden lacks it. The import gets the
# app's other fields back unchanged, through exported variables only.
ensure_generated() { # APP FIELD
  local item
  item="$(jq -r --arg a "$1" '.items[] | select(.app == $a) | .item' "${MANIFEST}")"
  [[ -n "${item}" ]] || die "$1 is not in ${MANIFEST}"
  [[ -z "$(field "${item}" "$2")" ]] || return 0
  (
    while IFS=$'\t' read -r name source; do
      if [[ "${source}" == "$2" ]]; then
        value="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
      else
        value="$(field "${item}" "${source}")"
        [[ -n "${value}" ]] || die "${item} has no ${source}"
      fi
      export "${name}=${value}"
    done < <(jq -r --arg a "$1" '.items[] | select(.app == $a) | .secrets[] | [.importEnv // .env, .field] | @tsv' "${MANIFEST}")
    exec "${IMPORT[@]}" --app "$1" --apply --update-existing
  )
  echo "✅ generated $2 in ${item}"
}

read_state() {
  local row app item name source
  MASTER_KEY="$(field nabla/prod/litellm LITELLM_MASTER_KEY)"
  [[ -n "${MASTER_KEY}" ]] || die "nabla/prod/litellm has no LITELLM_MASTER_KEY"
  CLIENT_KEY="$(field nabla/prod/litellm-mcp-client LITELLM_MCP_CLIENT_KEY)"
  VAULT=ok
  for row in "${GENERATED[@]}"; do
    app="${row%%|*}"
    item="$(jq -r --arg a "${app}" '.items[] | select(.app == $a) | .item' "${MANIFEST}")"
    [[ -n "$(field "${item}" "${row#*|}")" ]] || VAULT=drift
  done
  for row in "${DB_SERVERS[@]}"; do
    IFS='|' read -r _ _ _ item source _ _ <<<"${row}"
    [[ -n "$(field "${item}" "${source}")" ]] || VAULT=drift
  done
  RUNTIME=ok
  for app in "${RUNTIME_APPS[@]}"; do
    "${MATERIALIZE[@]}" --app "${app}" --verify >/dev/null 2>&1 || RUNTIME=drift
  done
  # Credentials come back redacted: compare the non-secret shape only.
  SERVERS=drift
  api "${MASTER_KEY}" GET /v1/mcp/server
  if [[ "${API_CODE}" == 200 ]] && jq -e --argjson want "$(desired_shapes)" '. as $have | all($want[];
      . as $w | ($have | map(select(.server_id == $w.server_id and .url == $w.url
        and .auth_type == $w.auth_type and .mcp_access_groups == $w.mcp_access_groups
        and ((.allowed_tools // []) | sort) == (($w.allowed_tools // []) | sort))) | length) == 1)' \
    <<<"${API_BODY}" >/dev/null 2>&1; then
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

[[ -n "$(field nabla/prod/grafana-observability GRAFANA_SERVICE_ACCOUNT_TOKEN)" ]] ||
  die "no Grafana MCP token yet: run scripts/grafana/mcp-identity.sh apply first"
for row in "${GENERATED[@]}"; do
  ensure_generated "${row%%|*}" "${row#*|}"
done
for app in "${RUNTIME_APPS[@]}"; do
  "${MATERIALIZE[@]}" --app "${app}" --install
done

# Upsert on every apply: credentials cannot be read back, so always resend them.
for row in "${DB_SERVERS[@]}"; do
  IFS='|' read -r name url auth item source tools desc <<<"${row}"
  upstream="$(field "${item}" "${source}")"
  [[ -n "${upstream}" ]] || die "${item} has no ${source}"
  payload="$(UPSTREAM_KEY="${upstream}" server_payload "${name}" "${url}" "${auth}" "${tools}" "${desc}")"
  api "${MASTER_KEY}" GET "/v1/mcp/server/${name}"
  if [[ "${API_CODE}" == 200 ]]; then method=PUT; else method=POST; fi
  api "${MASTER_KEY}" "${method}" /v1/mcp/server "${payload}"
  # LiteLLM answers 200/201 to POST and 202 to PUT.
  [[ "${API_CODE}" == 20[012] ]] || die "${method} MCP server ${name} failed (HTTP ${API_CODE})"
  echo "✅ MCP server ${name} (${method})"
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
