#!/usr/bin/env bash
# Read-only TrueNAS identity for the truenas-readonly MCP (check, then apply).
#
# The MCP needs its own API key: never the OpenTofu write key, nor Sample's
# observer key. apply creates the user mcp_readonly (READONLY_ADMIN through the
# builtin group truenas_readonly_administrators), one API key, the private key
# file read by scripts/mcp/truenas-readonly.sh and the Vaultwarden item
# nabla/prod/truenas-mcp-readonly. The key is never printed: it goes from
# midclt over SSH straight into a 600 file, then into Vaultwarden.
#
# Usage (owner terminal: TrueNAS ControlMaster open, Vaultwarden unlocked):
#   scripts/truenas/mcp-readonly-identity.sh check
#   scripts/truenas/mcp-readonly-identity.sh apply
set -euo pipefail

MODE="${1:-}"
USERNAME=mcp_readonly
KEY_NAME=truenas-mcp-readonly
RO_GID=951
KEY_FILE="${TRUENAS_MCP_KEY_FILE:-${XDG_CONFIG_HOME:-${HOME}/.config}/nabla/mcp/truenas-readonly.key}"
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
SSH_HOST="${TRUENAS_SSH_HOST:-truenas}"

case "${MODE}" in
  check | apply) ;;
  *)
    echo "usage: $0 check|apply" >&2
    exit 2
    ;;
esac

die() {
  echo "❌ $*" >&2
  exit 1
}

# Each argument is quoted for the remote shell, so JSON reaches midclt intact.
midclt() {
  ssh -o BatchMode=yes "${SSH_HOST}" "$(printf '%q ' midclt call "$@")" </dev/null
}

key_file_state() {
  if [[ ! -e "${KEY_FILE}" ]]; then
    echo absent
  elif [[ -L "${KEY_FILE}" || ! -s "${KEY_FILE}" ]] ||
    [[ "$(stat -c '%a %u' "${KEY_FILE}")" != "600 $(id -u)" ]]; then
    echo bad-mode
  else
    echo present
  fi
}

read_state() {
  RO_GROUP_ID="$(midclt group.query "[[\"gid\",\"=\",${RO_GID}]]" '{"get":true,"select":["id"]}' | jq -r .id)"
  [[ "${RO_GROUP_ID}" =~ ^[0-9]+$ ]] || die "group gid ${RO_GID} (truenas_readonly_administrators) not found"
  USER_JSON="$(midclt user.query "[[\"username\",\"=\",\"${USERNAME}\"]]" '{"select":["id","groups"]}')"
  USER_ID="$(jq -r '.[0].id // empty' <<<"${USER_JSON}")"
  IN_GROUP="$(jq -r --argjson g "${RO_GROUP_ID}" '(.[0].groups // []) | index($g) != null' <<<"${USER_JSON}")"
  mapfile -t KEY_IDS < <(midclt api_key.query "[[\"name\",\"=\",\"${KEY_NAME}\"],[\"revoked\",\"=\",false]]" '{"select":["id"]}' | jq -r '.[].id')
  KEY_FILE_STATE="$(key_file_state)"
}

report() {
  local user=absent group=missing key=absent status=DRIFT
  [[ -n "${USER_ID}" ]] && user=present
  [[ "${IN_GROUP}" == true ]] && group=member
  ((${#KEY_IDS[@]} > 0)) && key="present(${#KEY_IDS[@]})"
  if [[ "${user}" == present && "${group}" == member && ${#KEY_IDS[@]} -eq 1 && "${KEY_FILE_STATE}" == present ]]; then
    status=CONVERGED
  fi
  echo "MCP_IDENTITY user=${user} readonly_group=${group} api_key=${key} key_file=${KEY_FILE_STATE} status=${status}"
  [[ "${status}" == CONVERGED ]]
}

read_state
if [[ "${MODE}" == check ]]; then
  report || exit 3
  exit 0
fi

# Refuse before creating anything: a key nobody stored would be lost.
[[ -n "${BW_SESSION:-}" ]] || die "unlock Vaultwarden in this terminal first (BW_SESSION is empty)"

if [[ -z "${USER_ID}" ]]; then
  midclt user.create "$(jq -cn --arg u "${USERNAME}" --argjson g "${RO_GROUP_ID}" \
    '{username:$u, full_name:"TrueNAS MCP read-only", group_create:true, password_disabled:true,
      shell:"/usr/sbin/nologin", home:"/var/empty", smb:false, groups:[$g]}')" >/dev/null
  echo "✅ user ${USERNAME} created in truenas_readonly_administrators"
elif [[ "${IN_GROUP}" != true ]]; then
  midclt user.update "${USER_ID}" "$(jq -c --argjson g "${RO_GROUP_ID}" '{groups: ((.[0].groups // []) + [$g])}' <<<"${USER_JSON}")" >/dev/null
  echo "✅ user ${USERNAME} added to truenas_readonly_administrators"
fi

if [[ ${#KEY_IDS[@]} -ne 1 || "${KEY_FILE_STATE}" != present ]]; then
  # The key is shown only at creation: without the local copy, rotate it.
  for id in "${KEY_IDS[@]}"; do
    midclt api_key.delete "${id}" >/dev/null
  done
  install -d -m 700 "$(dirname -- "${KEY_FILE}")"
  tmp="$(mktemp "${KEY_FILE}.XXXXXX")"
  trap 'rm -f "${tmp}"' EXIT
  midclt api_key.create "$(jq -cn --arg n "${KEY_NAME}" --arg u "${USERNAME}" '{name:$n, username:$u}')" |
    jq -er '.key' >"${tmp}" || die "api_key.create returned no key"
  chmod 600 "${tmp}"
  mv -f "${tmp}" "${KEY_FILE}"
  trap - EXIT
  echo "✅ API key ${KEY_NAME} created; stored in ${KEY_FILE} (600)"
  TRUENAS_MCP_API_KEY="$(<"${KEY_FILE}")" python3 "${ROOT}/scripts/secrets/import_env_to_bitwarden.py" \
    --manifest "${ROOT}/config/secrets/manifest.json" --app truenas-mcp-readonly --apply --update-existing
fi

read_state
report
