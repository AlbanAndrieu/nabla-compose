#!/usr/bin/env bash
# Read-only DefectDojo identity for the DefectDojo MCP (check, then apply).
#
# The MCP acts as mcp-readonly: an active user that is neither staff nor
# superuser. Open-source DefectDojo dropped its roles (Reader is inert, RBAC moved
# to DefectDojo Pro): a plain user sees only the product types whose
# authorized_users list it, and may then also edit, add and import there (never
# delete, never staff or superuser actions). So the LiteLLM gateway exposes only
# its read tools (scripts/litellm/defectdojo-readonly-tools.json). apply lists the
# user on every product type through the Django ORM on TrueNAS (no API for it);
# check proves it sees every product the admin sees and cannot create a product
# type (403). apply authenticates as the admin (nabla/prod/defectdojo
# DD_ADMIN_USER and DD_ADMIN_PASSWORD, HTTP Basic: no token of the admin is reset)
# only to create the user or set a new random password, then
# trades that password for the user's token, which goes straight into Vaultwarden
# nabla/prod/mcp-defectdojo with the gateway bearer MCP_DEFECTDOJO_SERVER_TOKEN.
# No value is ever printed, and none reaches a command line.
#
# Usage (owner terminal: Vaultwarden unlocked, TrueNAS ControlMaster open):
#   scripts/defectdojo/mcp-identity.sh check
#   scripts/defectdojo/mcp-identity.sh apply
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
DD_URL=http://172.17.0.24:31085
USER_NAME=mcp-readonly
SSH_HOST="${TRUENAS_SSH_HOST:-truenas}"
ITEM=nabla/prod/mcp-defectdojo
IMPORT=("python3" "${ROOT}/scripts/secrets/import_env_to_bitwarden.py" --manifest "${ROOT}/config/secrets/manifest.json")

die() {
  echo "❌ $*" >&2
  exit 1
}

[[ -n "${BW_SESSION:-}" ]] || die "unlock Vaultwarden in this terminal first (BW_SESSION is empty)"

field() { bw_field "$1" "$2" 2>/dev/null || true; }

# DefectDojo API (LAN only). Credentials go through a curl config on a file
# descriptor and the JSON body through stdin: neither is ever in an argv.
api() { # CURL_AUTH_LINE METHOD PATH [JSON]; sets API_CODE and API_BODY
  local out data=()
  [[ $# -lt 4 ]] || data=(--data-binary @-)
  out="$(printf '%s' "${4:-}" |
    curl -sS --noproxy '*' -m 30 -K <(printf '%s\n' "$1") -X "$2" \
      -H 'Content-Type: application/json' "${data[@]}" \
      -w '\n%{http_code}' "${DD_URL}$3")" || die "curl $2 $3 failed (exit $?)"
  API_CODE="${out##*$'\n'}"
  API_BODY="${out%$'\n'*}"
}

# authorized_users of every product type, through the ORM (no API); idempotent, no secret.
grant_view() {
  ssh -o BatchMode=yes "${SSH_HOST}" "sudo -n docker exec -i defectdojo-uwsgi python manage.py shell" >/dev/null <<'PY'
from dojo.models import Dojo_User, Global_Role, Product_Type
user = Dojo_User.objects.get(username="mcp-readonly")
Global_Role.objects.filter(user=user).delete()  # inert in open-source DefectDojo
for product_type in Product_Type.objects.all():
    product_type.authorized_users.add(user)
PY
}

read_state() {
  local admin_user admin_secret
  admin_user="$(field nabla/prod/defectdojo DD_ADMIN_USER)"
  admin_secret="$(field nabla/prod/defectdojo DD_ADMIN_PASSWORD)"
  [[ -n "${admin_user}" && -n "${admin_secret}" ]] || die "nabla/prod/defectdojo lacks the admin login"
  [[ "${admin_user}${admin_secret}" != *[\"\\]* ]] || die "the admin login holds a quote or backslash"
  ADMIN="user = \"${admin_user}:${admin_secret}\""
  api "${ADMIN}" GET "/api/v2/users/?username=${USER_NAME}"
  [[ "${API_CODE}" == 200 ]] || die "DefectDojo refused the admin login (HTTP ${API_CODE})"
  USER_ID="$(jq -r --arg u "${USER_NAME}" '[.results[] | select(.username == $u)][0].id // empty' <<<"${API_BODY}")"
  PRIVILEGED="$(jq -r --arg u "${USER_NAME}" '[.results[] | select(.username == $u)][0] | ((.is_staff // false) or (.is_superuser // false))' <<<"${API_BODY}")"
  api "${ADMIN}" GET "/api/v2/products/?limit=1"
  ALL="$(jq -r '.count // 0' <<<"${API_BODY}")"
  KEY="$(field "${ITEM}" DEFECTDOJO_API_KEY)"
  KEY_STATE=absent READ=0 WRITE=unknown
  if [[ -n "${KEY}" ]]; then
    api "header = \"Authorization: Token ${KEY}\"" GET /api/v2/user_profile/
    if [[ "${API_CODE}" == 200 && "$(jq -r '.user.username' <<<"${API_BODY}")" == "${USER_NAME}" ]]; then
      KEY_STATE=valid
      api "header = \"Authorization: Token ${KEY}\"" GET "/api/v2/products/?limit=1"
      READ="$(jq -r '.count // 0' <<<"${API_BODY}")"
      # An empty body: a 403 means no write right, a 400 would mean the write was allowed.
      api "header = \"Authorization: Token ${KEY}\"" POST /api/v2/product_types/ '{}'
      if [[ "${API_CODE}" == 403 ]]; then WRITE=denied; else WRITE="allowed(HTTP ${API_CODE})"; fi
    else
      KEY_STATE=invalid
    fi
  fi
}

report() {
  local status=DRIFT user=absent
  [[ -z "${USER_ID}" ]] || user="present(privileged=${PRIVILEGED})"
  # It must see every product the admin sees, without staff or creation rights.
  if [[ -n "${USER_ID}" && "${PRIVILEGED}" == false && "${KEY_STATE}" == valid && "${READ}" == "${ALL}" && "${WRITE}" == denied ]]; then
    status=CONVERGED
  fi
  echo "MCP_DEFECTDOJO user=${user} key=${KEY_STATE} products_visible=${READ}/${ALL} product_type_create=${WRITE} status=${status}"
  [[ "${status}" == CONVERGED ]]
}

read_state
if [[ "${MODE}" == check ]]; then
  report || exit 3
  exit 0
fi

if [[ "${KEY_STATE}" != valid || "${PRIVILEGED}" != false ]]; then
  password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  if [[ -z "${USER_ID}" ]]; then
    api "${ADMIN}" POST /api/v2/users/ "$(PW="${password}" jq -cn --arg u "${USER_NAME}" '{username: $u,
      password: $ENV.PW, email: "mcp-readonly@albandrieu.invalid", first_name: "MCP", last_name: "read-only",
      is_active: true, is_staff: false, is_superuser: false}')"
    [[ "${API_CODE}" == 201 ]] || die "user creation failed (HTTP ${API_CODE})"
  else
    api "${ADMIN}" PATCH "/api/v2/users/${USER_ID}/" "$(PW="${password}" jq -cn '{password: $ENV.PW,
      is_active: true, is_staff: false, is_superuser: false}')"
    [[ "${API_CODE}" == 200 ]] || die "user update failed (HTTP ${API_CODE})"
  fi
  # The password reaches jq through its environment, never its argv.
  out="$(PW="${password}" jq -cn --arg u "${USER_NAME}" '{username: $u, password: $ENV.PW}' |
    curl -sS --noproxy '*' -m 30 -H 'Content-Type: application/json' --data-binary @- \
      -w '\n%{http_code}' "${DD_URL}/api/v2/api-token-auth/")" || die "token request failed"
  [[ "${out##*$'\n'}" == 200 ]] || die "token request refused (HTTP ${out##*$'\n'})"
  key="$(jq -er '.token' <<<"${out%$'\n'*}")" || die "token request returned no token"
  unset password out
  # The gateway bearer shares the item: keep it, or create it with the key.
  server_token="$(field "${ITEM}" MCP_DEFECTDOJO_SERVER_TOKEN)"
  [[ -n "${server_token}" ]] || server_token="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  MCP_DEFECTDOJO_API_KEY="${key}" MCP_DEFECTDOJO_SERVER_TOKEN="${server_token}" \
    "${IMPORT[@]}" --app mcp-defectdojo --apply --update-existing
  unset key server_token
  echo "✅ ${USER_NAME} token in ${ITEM}"
  read_state
fi

if [[ "${READ}" != "${ALL}" ]]; then
  grant_view
  echo "✅ ${USER_NAME} listed on every product type"
fi

read_state
report
