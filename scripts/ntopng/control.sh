#!/usr/bin/env bash
# ntopng control identities and configuration as code (check, then apply).
#
# Two administrator users, each with its own API token. ntopng has no finer
# role: its MCP endpoint and every REST write require administrator.
#   - nabla-control: OpenTofu (infrastructure/ntopng) and API scripts,
#     Vaultwarden nabla/prod/ntopng-control, NTOPNG_CONTROL_TOKEN;
#   - nabla-mcp: the LiteLLM MCP gateway (scripts/litellm/mcp-gateway.sh, read-only
#     tool list), Vaultwarden nabla/prod/ntopng-mcp, NTOPNG_MCP_TOKEN.
# apply creates a missing user with the admin password of nabla/prod/ntopng (the
# new user's own random password is never kept: its token is the credential),
# mints a token when Vaultwarden has none or ntopng rejects it, stores it straight
# into Vaultwarden, then applies infrastructure/ntopng with the nabla-control token.
# No value is ever printed, and none reaches a command line.
#
# Usage (owner terminal: Vaultwarden unlocked, Garage state keys exported):
#   scripts/ntopng/control.sh check
#   scripts/ntopng/control.sh apply
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
# Fixed TrueNAS ntopng: an inherited URL must not redirect the admin credential.
NTOPNG_URL=http://172.17.0.24:31080
IMPORT=("python3" "${ROOT}/scripts/secrets/import_env_to_bitwarden.py" --manifest "${ROOT}/config/secrets/manifest.json")
# user|manifest app|Vaultwarden item|field (also the importEnv name)
IDENTITIES=(
  "nabla-control|ntopng-control|nabla/prod/ntopng-control|NTOPNG_CONTROL_TOKEN"
  "nabla-mcp|ntopng-mcp|nabla/prod/ntopng-mcp|NTOPNG_MCP_TOKEN"
)

die() {
  echo "❌ $*" >&2
  exit 1
}

[[ -n "${BW_SESSION:-}" ]] || die "unlock Vaultwarden in this terminal first (BW_SESSION is empty)"

# ntopng REST API (LAN only). The credential goes through a curl config on a file
# descriptor and the JSON body through stdin: neither is ever in an argv.
api() { # CURL_AUTH_LINE METHOD PATH [JSON]; sets API_CODE, API_BODY and API_OK
  local out data=()
  [[ $# -lt 4 ]] || data=(--data-binary @-)
  out="$(printf '%s' "${4:-}" |
    curl -sS --noproxy '*' -K <(printf '%s\n' "$1") -X "$2" \
      -H 'Content-Type: application/json' "${data[@]}" \
      -w '\n%{http_code}' "${NTOPNG_URL}$3")" || die "curl $2 $3 failed (exit $?)"
  API_CODE="${out##*$'\n'}"
  API_BODY="${out%$'\n'*}"
  API_OK=false
  if [[ "${API_CODE}" == 200 ]] && jq -e '.rc == 0' <<<"${API_BODY}" >/dev/null 2>&1; then API_OK=true; fi
}

token_auth() { printf 'header = "Authorization: Token %s"' "$1"; }

tofu_run() { # terragrunt arguments
  local token key secret lan=172.17.0.24,.int.albandrieu.com
  token="$(bw_field nabla/prod/ntopng-control NTOPNG_CONTROL_TOKEN)" || die "nabla/prod/ntopng-control has no NTOPNG_CONTROL_TOKEN"
  # Garage state keys: the exported ones win, else Vaultwarden (as in terraform/nexus).
  key="${GARAGE_OPENTOFU_AWS_ACCESS_KEY_ID:-}" secret="${GARAGE_OPENTOFU_AWS_SECRET_ACCESS_KEY:-}"
  if [[ -z "${key}" || -z "${secret}" ]]; then
    key="$(bw_field nabla/prod/infrastructure-bootstrap AWS_ACCESS_KEY_ID)" || die "no Garage state key"
    secret="$(bw_field nabla/prod/infrastructure-bootstrap AWS_SECRET_ACCESS_KEY)" || die "no Garage state secret"
  fi
  # ntopng and the Garage state backend (s3.int) are LAN-only: bypass any shell proxy.
  TF_VAR_ntopng_token="${token}" GARAGE_OPENTOFU_AWS_ACCESS_KEY_ID="${key}" GARAGE_OPENTOFU_AWS_SECRET_ACCESS_KEY="${secret}" \
    NO_PROXY="${lan},${NO_PROXY:-}" no_proxy="${lan},${no_proxy:-}" \
    bash "${ROOT}/scripts/infra/terragrunt-safe.sh" infrastructure/ntopng "$@"
}

read_state() {
  local row user item field token
  ADMIN_PW="$(bw_field nabla/prod/ntopng NTOPNG_ADMIN_PASSWORD 2>/dev/null)" || die "nabla/prod/ntopng has no NTOPNG_ADMIN_PASSWORD"
  [[ "${ADMIN_PW}" != *[\"\\]* ]] || die "NTOPNG_ADMIN_PASSWORD holds a quote or backslash; regenerate it"
  ADMIN_AUTH="user = \"admin:${ADMIN_PW}\""
  # Administrator-only endpoint: a token that reads it is valid and administrator.
  api "${ADMIN_AUTH}" GET /lua/rest/v2/get/ntopng/users.lua
  [[ "${API_OK}" == true ]] || die "ntopng refuses the Vaultwarden admin password (HTTP ${API_CODE})"
  USERS="${API_BODY}"
  STATES=()
  for row in "${IDENTITIES[@]}"; do
    IFS='|' read -r user _ item field <<<"${row}"
    state=absent
    if jq -e --arg u "${user}" '.rsp | has($u)' <<<"${USERS}" >/dev/null; then state="no-token"; fi
    token="$(bw_field "${item}" "${field}" 2>/dev/null)" || token=""
    if [[ "${state}" != absent && -n "${token}" ]]; then
      api "$(token_auth "${token}")" GET /lua/rest/v2/get/ntopng/users.lua
      if [[ "${API_OK}" == true ]]; then state=ok; else state="token-rejected"; fi
    fi
    STATES+=("${state}")
  done
  CONFIG=no-token
  if bw_field nabla/prod/ntopng-control NTOPNG_CONTROL_TOKEN >/dev/null 2>&1; then
    local rc=0
    tofu_run plan -detailed-exitcode -input=false -lock=false >/dev/null 2>&1 || rc=$?
    case "${rc}" in
      0) CONFIG=ok ;;
      2) CONFIG=drift ;;
      *) CONFIG=error ;;
    esac
  fi
}

report() {
  local i status=CONVERGED line="NTOPNG_CONTROL"
  for i in "${!IDENTITIES[@]}"; do
    line+=" ${IDENTITIES[i]%%|*}=${STATES[i]}"
    [[ "${STATES[i]}" == ok ]] || status=DRIFT
  done
  [[ "${CONFIG}" == ok ]] || status=DRIFT
  echo "${line} opentofu=${CONFIG} status=${status}"
  [[ "${status}" == CONVERGED ]]
}

read_state
if [[ "${MODE}" == check ]]; then
  report || exit 3
  exit 0
fi

for i in "${!IDENTITIES[@]}"; do
  IFS='|' read -r user app item field <<<"${IDENTITIES[i]}"
  if [[ "${STATES[i]}" == absent ]]; then
    body="$(PW="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" jq -nc --arg u "${user}" '{
      username: $u, full_name: ("Nabla " + $u), password: $ENV.PW, confirm_password: $ENV.PW,
      user_role: "administrator", allowed_networks: "0.0.0.0/0,::/0", allowed_interface: ""}')"
    api "${ADMIN_AUTH}" POST /lua/rest/v2/add/ntopng/user.lua "${body}"
    unset body
    [[ "${API_OK}" == true ]] || die "creating ntopng user ${user} failed (HTTP ${API_CODE})"
    echo "✅ ntopng user ${user} created (administrator)"
  fi
  if [[ "${STATES[i]}" != ok ]]; then
    # Without a working Vaultwarden copy, mint a new token (the old one is lost).
    api "${ADMIN_AUTH}" POST /lua/rest/v2/create/ntopng/api_token.lua "$(jq -nc --arg u "${user}" '{username: $u}')"
    [[ "${API_OK}" == true ]] || die "minting the ${user} token failed (HTTP ${API_CODE})"
    token="$(jq -er '.rsp.api_token' <<<"${API_BODY}")" || die "ntopng returned no token for ${user}"
    # export is a builtin: the token reaches the importer environment, never an argv.
    (
      export "${field}=${token}"
      exec "${IMPORT[@]}" --app "${app}" --apply --update-existing
    )
    unset token
    echo "✅ ${user} token stored in ${item}"
  fi
done

tofu_run apply -auto-approve -input=false
read_state
report
