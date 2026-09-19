#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
APP="${2:-}"
SOURCE="${3:-}"
RUNTIME_ROOT="${NABLA_RUNTIME_ENV_ROOT:-/mnt/cpool/secrets/runtime}"
RUNTIME_FILE="${NABLA_RUNTIME_SECRET_FILE:-.env.secrets}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  echo "usage: sudo env -u BW_SESSION bash $0 [--check|--apply|--compare] <app> [source-file]"
}

case "${MODE}" in
  --check | --apply | --compare) ;;
  *) usage >&2; exit 2 ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run as root"
[[ -z "${BW_SESSION:-}" ]] || fail "refusing privileged execution with BW_SESSION in environment"
[[ "${APP}" =~ ^[a-z0-9][a-z0-9-]*$ ]] || fail "invalid app identifier: ${APP:-<missing>}"
[[ "${RUNTIME_FILE}" =~ ^[.]env([.][a-z0-9-]+)?([.]secrets)?$ ]] ||
  fail "invalid runtime secret filename: ${RUNTIME_FILE}"
[[ "${RUNTIME_FILE}" != *"/"* ]] || fail "runtime secret filename must be a basename"

TARGET_DIR="${RUNTIME_ROOT}/${APP}"
TARGET="${TARGET_DIR}/${RUNTIME_FILE}"

check_target() {
  [[ -f "${TARGET}" && ! -L "${TARGET}" ]] || fail "missing/non-regular runtime secret file: ${TARGET}"
  [[ -s "${TARGET}" ]] || fail "empty runtime secret file: ${TARGET}"
  metadata="$(stat -c '%U:%G %a' "${TARGET}")"
  [[ "${metadata}" == "root:root 600" ]] ||
    fail "${TARGET} owner/mode=${metadata}; expected root:root 600"
}

if [[ "${MODE}" == "--check" ]]; then
  check_target
  printf 'OK: runtime secret file app=%s path=%s\n' "${APP}" "${TARGET}"
  exit 0
fi

[[ -n "${SOURCE}" ]] || fail "source file required for ${MODE}"
[[ -f "${SOURCE}" && ! -L "${SOURCE}" ]] || fail "source must be a regular non-symlink file"
[[ -s "${SOURCE}" ]] || fail "source file is empty"

if [[ "${MODE}" == "--compare" ]]; then
  check_target
  cmp -s "${SOURCE}" "${TARGET}" ||
    fail "${APP}: candidate differs from installed runtime materialization"
  printf 'OK: candidate matches installed runtime materialization app=%s\n' "${APP}"
  exit 0
fi

umask 077
install -d -o root -g root -m 700 "${TARGET_DIR}"
tmp="$(mktemp "${TARGET_DIR}/.env.secrets.tmp.XXXXXX")"
trap 'rm -f "${tmp}"' EXIT
install -o root -g root -m 600 "${SOURCE}" "${tmp}"
[[ -s "${tmp}" ]] || fail "staged runtime secret file is empty"
mv -f "${tmp}" "${TARGET}"
trap - EXIT
check_target
printf 'OK: installed runtime secret file app=%s path=%s\n' "${APP}" "${TARGET}"
