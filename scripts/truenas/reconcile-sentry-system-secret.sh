#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

MODE="${1:---check}"
LEGACY_FILE="${SENTRY_SECRET_FILE:-/mnt/cpool/sentry/.env.secrets}"
CANONICAL_FILE="${SENTRY_CANONICAL_SECRET_FILE:-/mnt/cpool/secrets/runtime/sentry/.env.secrets}"

case "${MODE}" in
  --check | --apply) ;;
  -h | --help)
    printf 'usage: sudo bash scripts/truenas/reconcile-sentry-system-secret.sh [--check|--apply]\n'
    exit 0
    ;;
  *)
    fail "unknown mode: ${MODE}"
    ;;
esac

require_root "run as root on TrueNAS"
require_commands awk install mktemp openssl stat

read_key() {
  local file="$1" key="$2"
  [[ -f "${file}" ]] || return 0
  awk -F= -v key="${key}" '
    $1 == key {
      sub(/^[^=]*=/, "")
      print
      exit
    }
  ' "${file}"
}

system_secret_from() {
  local file="$1" value
  value="$(read_key "${file}" SENTRY_SECRET_KEY)"
  if [[ -z "${value}" ]]; then
    value="$(read_key "${file}" SENTRY_SYSTEM_SECRET_KEY)"
  fi
  printf '%s' "${value}"
}

[[ -f "${LEGACY_FILE}" ]] ||
  fail "Sentry runtime secret file missing: ${LEGACY_FILE}"

legacy_secret="$(system_secret_from "${LEGACY_FILE}")"
canonical_secret=""
if [[ -f "${CANONICAL_FILE}" ]]; then
  canonical_secret="$(system_secret_from "${CANONICAL_FILE}")"
fi

if [[ -n "${legacy_secret}" && -n "${canonical_secret}" &&
      "${legacy_secret}" != "${canonical_secret}" ]]; then
  fail "Sentry system secret conflicts between legacy and canonical runtime files; refusing automatic rotation"
fi

if [[ "${MODE}" == "--check" ]]; then
  if [[ -n "${legacy_secret}" ]]; then
    ok "Sentry runtime system secret is present without printing it"
    if [[ -n "${canonical_secret}" ]]; then
      ok "canonical Sentry system secret matches the active legacy runtime value"
    else
      printf 'WARN: canonical Sentry runtime file has no system secret yet; restage after runtime acceptance\n'
    fi
    exit 0
  fi

  if [[ -n "${canonical_secret}" ]]; then
    fail "active legacy Sentry runtime file is missing the system secret while the canonical staged file still has it; run --apply to restore it"
  fi

  fail "SENTRY_SECRET_KEY/SENTRY_SYSTEM_SECRET_KEY is missing from both active and canonical Sentry runtime files"
fi

generated=0
secret="${legacy_secret:-${canonical_secret:-}}"
if [[ -z "${secret}" ]]; then
  secret="$(openssl rand -hex 32)"
  generated=1
fi

tmp="$(mktemp /mnt/cpool/sentry/.env.secrets.tmp.XXXXXX)"
trap 'rm -f "${tmp}"' EXIT

awk -F= '
  $1 != "SENTRY_SECRET_KEY" { print }
' "${LEGACY_FILE}" >"${tmp}"
printf 'SENTRY_SECRET_KEY=%s\n' "${secret}" >>"${tmp}"

install -o root -g root -m 600 "${tmp}" "${LEGACY_FILE}"
rm -f "${tmp}"
trap - EXIT
unset legacy_secret canonical_secret secret

if ((generated == 1)); then
  printf 'Generated a new Sentry system secret because neither active nor canonical runtime material contained one; value not printed.\n'
else
  printf 'Restored/preserved the existing Sentry system secret without printing it.\n'
fi

bash "${BASH_SOURCE[0]}" --check
printf 'NEXT: after Sentry runtime acceptance, refresh the canonical staged copy with:\n'
printf '  sudo bash scripts/truenas/bootstrap-repository-env-files.sh --restage sentry\n'
