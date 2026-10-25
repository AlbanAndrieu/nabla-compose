#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
APP="${2:-}"
SOURCE="${3:-}"

# shellcheck source=../lib/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../lib/common.sh"

case "${MODE}" in
  --install | --verify) ;;
  *) fail "usage: sudo $0 [--install|--verify] <app> <rendered-file>" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run through sudo; Vaultwarden credentials must remain in the unprivileged caller"
[[ "${APP}" =~ ^[a-z0-9][a-z0-9-]*$ ]] || fail "invalid app id: ${APP:-<missing>}"
[[ -n "${SOURCE}" ]] || fail "rendered source file is required"
[[ -f "${SOURCE}" && ! -L "${SOURCE}" ]] || fail "source must be a regular non-symlink file"
[[ -s "${SOURCE}" ]] || fail "source rendered file is empty"

source_mode="$(stat -c '%a' "${SOURCE}")"
[[ "${source_mode}" == "600" ]] || fail "source mode=${source_mode}; expected 600"
source_uid="$(stat -c '%u' "${SOURCE}")"
if [[ -n "${SUDO_UID:-}" && "${source_uid}" != "${SUDO_UID}" ]]; then
  fail "source owner uid=${source_uid}; expected sudo caller uid=${SUDO_UID}"
fi

DEST_DIR="/mnt/cpool/secrets/runtime/${APP}"
DEST="${DEST_DIR}/.env.secrets"

# Verification must not create directories or modify target ownership.
# Refuse a symlinked destination directory before either mode.
[[ ! -L "${DEST_DIR}" ]] || fail "runtime secret directory must not be a symlink"
[[ ! -e "${DEST_DIR}" || -d "${DEST_DIR}" ]] ||
  fail "runtime secret directory is not a directory"

if [[ "${MODE}" == "--install" ]]; then
  install -d -o root -g root -m 700 "${DEST_DIR}"
  tmp="$(mktemp "${DEST_DIR}/.env.secrets.tmp.XXXXXX")"
  trap 'rm -f "${tmp:-}"' EXIT
  install -o root -g root -m 600 "${SOURCE}" "${tmp}"
  cmp -s "${SOURCE}" "${tmp}" || fail "copy verification failed before atomic replace"
  mv -f "${tmp}" "${DEST}"
  trap - EXIT
fi

[[ -f "${DEST}" && ! -L "${DEST}" ]] || fail "runtime materialization missing: ${DEST}"
[[ -s "${DEST}" ]] || fail "runtime materialization is empty: ${DEST}"
metadata="$(stat -c '%U:%G %a' "${DEST}")"
[[ "${metadata}" == "root:root 600" ]] ||
  fail "${DEST} owner/mode=${metadata}; expected root:root 600"
cmp -s "${SOURCE}" "${DEST}" ||
  fail "${APP}: rendered Vaultwarden material differs from runtime materialization"

printf 'OK: runtime secret %s app=%s target=%s\n' "${MODE#--}" "${APP}" "${DEST}"
