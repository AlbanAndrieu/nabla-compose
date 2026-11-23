#!/usr/bin/env bash
# Temporary bridge for the OpenTofu drift check (roadmap: replace with a
# dedicated read-only Garage key): copy the current Garage key "opentofu"
# (RWO on opentofu-state, already readable by root through the garage
# container) into the check's root-only common.env. The secret goes from
# `garage key info --show-secret` to the file and is never printed.
set -euo pipefail

MODE="${1:-}"
KEY_NAME="opentofu"
ENV_DIR="/mnt/cpool/secrets/runtime/opentofu-drift"
DEST="${ENV_DIR}/common.env"

fail() {
  echo "REJECTED: $*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *)
    echo "usage: sudo $0 --check|--apply" >&2
    exit 2
    ;;
esac
[[ "${EUID}" -eq 0 ]] || fail "run through sudo"

key_info() { docker exec garage /garage key info "$@" "${KEY_NAME}" 2>/dev/null; }
field() { awk -F': *' -v name="$1" '$1 == name { print $2; exit }'; }

info="$(key_info)" || fail "garage key ${KEY_NAME} not found"
grep -Eq '^R[WO]* +[0-9a-f]+ +opentofu-state( |$)' <<<"${info}" ||
  fail "garage key ${KEY_NAME} cannot read opentofu-state"
key_id="$(field "Key ID" <<<"${info}")"
[[ "${key_id}" =~ ^GK[0-9a-f]+$ ]] || fail "unexpected key id format"

installed_id=""
if [[ -f "${DEST}" && ! -L "${DEST}" ]]; then
  [[ "$(stat -c '%U:%G %a' "${DEST}")" == "root:root 600" ]] || fail "${DEST} is not root:root 600"
  installed_id="$(sed -n 's/^GARAGE_OPENTOFU_AWS_ACCESS_KEY_ID=//p' "${DEST}")"
fi

if [[ "${installed_id}" == "${key_id}" ]]; then
  echo "OK: ${DEST} holds the current Garage key ${KEY_NAME}"
  exit 0
fi
if [[ "${MODE}" == "--check" ]]; then
  echo "CHECK: ${DEST} would be (re)written from Garage key ${KEY_NAME}"
  exit 0
fi

secret_info="$(key_info --show-secret)" || fail "garage key info --show-secret failed"
secret="$(field "Secret key" <<<"${secret_info}")"
unset secret_info
[[ "${secret}" =~ ^[0-9a-f]{32,}$ ]] || fail "unexpected secret format (value not shown)"
install -d -o root -g root -m 700 "${ENV_DIR}"
tmp="$(mktemp "${ENV_DIR}/.common.env.XXXXXX")" # mktemp creates it 0600
trap 'rm -f "${tmp}"' EXIT
# printf is a builtin: the secret never appears in a process argument list.
printf 'GARAGE_OPENTOFU_AWS_ACCESS_KEY_ID=%s\nGARAGE_OPENTOFU_AWS_SECRET_ACCESS_KEY=%s\n' \
  "${key_id}" "${secret}" >"${tmp}"
mv -f "${tmp}" "${DEST}"
trap - EXIT
echo "APPLIED: ${DEST} written from Garage key ${KEY_NAME} (root:root 600)"
