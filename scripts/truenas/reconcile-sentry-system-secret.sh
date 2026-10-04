#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

MODE="${1:---check}"
LEGACY_FILE="${SENTRY_SECRET_FILE:-/mnt/cpool/sentry/.env.secrets}"
CANONICAL_FILE="${SENTRY_CANONICAL_SECRET_FILE:-/mnt/cpool/secrets/runtime/sentry/.env.secrets}"
RELAY_IMAGE="${SENTRY_RELAY_IMAGE:-ghcr.io/getsentry/relay:26.8.0}"

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
require_commands awk docker install jq mktemp openssl stat

read_key() {
  local file="$1" key="$2"
  [[ -f "${file}" ]] || return 0
  awk -F= -v key="${key}" '
    $1 == key {
      sub(/^[^=]*=/, "")
      value = $0
      first = substr(value, 1, 1)
      last = substr(value, length(value), 1)
      quote = sprintf("%c", 39)
      if ((first == quote && last == quote) || (first == "\"" && last == "\"")) {
        value = substr(value, 2, length(value) - 2)
      }
      print value
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


relay_credentials_state() {
  local file="$1" present=0
  [[ -n "$(read_key "${file}" RELAY_ID)" ]] && present=$((present + 1))
  [[ -n "$(read_key "${file}" RELAY_PUBLIC_KEY)" ]] && present=$((present + 1))
  [[ -n "$(read_key "${file}" RELAY_SECRET_KEY)" ]] && present=$((present + 1))
  case "${present}" in
    0) printf 'missing\n' ;;
    3) printf 'complete\n' ;;
    *) printf 'partial\n' ;;
  esac
}

relay_credentials_match() {
  local left="$1" right="$2"
  [[ "$(read_key "${left}" RELAY_ID)" == "$(read_key "${right}" RELAY_ID)" &&
     "$(read_key "${left}" RELAY_PUBLIC_KEY)" == "$(read_key "${right}" RELAY_PUBLIC_KEY)" &&
     "$(read_key "${left}" RELAY_SECRET_KEY)" == "$(read_key "${right}" RELAY_SECRET_KEY)" ]]
}

[[ -f "${LEGACY_FILE}" ]] ||
  fail "Sentry runtime secret file missing: ${LEGACY_FILE}"

legacy_secret="$(system_secret_from "${LEGACY_FILE}")"
canonical_secret=""
legacy_relay_state="$(relay_credentials_state "${LEGACY_FILE}")"
canonical_relay_state="missing"
if [[ -f "${CANONICAL_FILE}" ]]; then
  canonical_secret="$(system_secret_from "${CANONICAL_FILE}")"
  canonical_relay_state="$(relay_credentials_state "${CANONICAL_FILE}")"
fi

if [[ -n "${legacy_secret}" && -n "${canonical_secret}" &&
      "${legacy_secret}" != "${canonical_secret}" ]]; then
  fail "Sentry system secret conflicts between legacy and canonical runtime files; refusing automatic rotation"
fi
[[ "${legacy_relay_state}" != "partial" ]] ||
  fail "active Sentry Relay credential set is partial; refusing automatic replacement"
[[ "${canonical_relay_state}" != "partial" ]] ||
  fail "canonical Sentry Relay credential set is partial; refusing staged restore"
if [[ "${legacy_relay_state}" == "complete" &&
      "${canonical_relay_state}" == "complete" ]] &&
  ! relay_credentials_match "${LEGACY_FILE}" "${CANONICAL_FILE}"; then
  fail "Sentry Relay credentials conflict between active and canonical runtime files"
fi

if [[ "${MODE}" == "--check" ]]; then
  [[ -n "${legacy_secret}" ]] ||
    fail "SENTRY_SECRET_KEY/SENTRY_SYSTEM_SECRET_KEY is missing from active Sentry runtime material"
  [[ "${legacy_relay_state}" == "complete" ]] ||
    fail "RELAY_ID/RELAY_PUBLIC_KEY/RELAY_SECRET_KEY are missing from active Sentry runtime material"
  ok "Sentry runtime system secret is present without printing it"
  ok "Sentry Relay credential set is complete without printing it"
  if [[ -n "${canonical_secret}" ]]; then
    ok "canonical Sentry system secret matches the active legacy runtime value"
  else
    printf 'WARN: canonical Sentry runtime file has no system secret yet; restage after runtime acceptance\n'
  fi
  if [[ "${canonical_relay_state}" == "complete" ]]; then
    ok "canonical Sentry Relay credentials match the active runtime value"
  else
    printf 'WARN: canonical Sentry runtime file has no Relay credentials yet; restage after runtime acceptance\n'
  fi
  exit 0
fi

generated_system=0
generated_relay=0
secret="${legacy_secret:-${canonical_secret:-}}"
if [[ -z "${secret}" ]]; then
  secret="$(openssl rand -hex 32)"
  generated_system=1
fi

relay_id=""
relay_public_key=""
relay_secret_key=""
if [[ "${legacy_relay_state}" == "complete" ]]; then
  relay_id="$(read_key "${LEGACY_FILE}" RELAY_ID)"
  relay_public_key="$(read_key "${LEGACY_FILE}" RELAY_PUBLIC_KEY)"
  relay_secret_key="$(read_key "${LEGACY_FILE}" RELAY_SECRET_KEY)"
elif [[ "${canonical_relay_state}" == "complete" ]]; then
  relay_id="$(read_key "${CANONICAL_FILE}" RELAY_ID)"
  relay_public_key="$(read_key "${CANONICAL_FILE}" RELAY_PUBLIC_KEY)"
  relay_secret_key="$(read_key "${CANONICAL_FILE}" RELAY_SECRET_KEY)"
else
  docker image inspect "${RELAY_IMAGE}" >/dev/null 2>&1 ||
    fail "Relay image is not available locally: ${RELAY_IMAGE}; pull the pinned image before --apply"
  relay_tmp="$(mktemp /mnt/cpool/sentry/.relay-credentials.tmp.XXXXXX)"
  trap 'rm -f "${relay_tmp:-}"' EXIT
  chmod 600 "${relay_tmp}"
  docker run --rm --network none "${RELAY_IMAGE}" credentials generate --stdout >"${relay_tmp}"
  jq -e '
    (.id | type == "string" and length > 0) and
    (.public_key | type == "string" and length > 0) and
    (.secret_key | type == "string" and length > 0)
  ' "${relay_tmp}" >/dev/null ||
    fail "Relay generated an invalid credential set"
  relay_id="$(jq -r '.id' "${relay_tmp}")"
  relay_public_key="$(jq -r '.public_key' "${relay_tmp}")"
  relay_secret_key="$(jq -r '.secret_key' "${relay_tmp}")"
  rm -f "${relay_tmp}"
  trap - EXIT
  generated_relay=1
fi

tmp="$(mktemp /mnt/cpool/sentry/.env.secrets.tmp.XXXXXX)"
trap 'rm -f "${tmp}"' EXIT

awk -F= '
  $1 != "SENTRY_SECRET_KEY" &&
  $1 != "SENTRY_SYSTEM_SECRET_KEY" &&
  $1 != "RELAY_ID" &&
  $1 != "RELAY_PUBLIC_KEY" &&
  $1 != "RELAY_SECRET_KEY" { print }
' "${LEGACY_FILE}" >"${tmp}"
printf 'SENTRY_SECRET_KEY=%s\n' "${secret}" >>"${tmp}"
printf 'RELAY_ID=%s\n' "${relay_id}" >>"${tmp}"
printf 'RELAY_PUBLIC_KEY=%s\n' "${relay_public_key}" >>"${tmp}"
printf 'RELAY_SECRET_KEY=%s\n' "${relay_secret_key}" >>"${tmp}"

install -o root -g root -m 600 "${tmp}" "${LEGACY_FILE}"
rm -f "${tmp}"
trap - EXIT
unset legacy_secret canonical_secret secret relay_id relay_public_key relay_secret_key

if ((generated_system == 1)); then
  printf 'Generated a new Sentry system secret because no accepted runtime value existed; value not printed.\n'
else
  printf 'Restored/preserved the existing Sentry system secret without printing it.\n'
fi
if ((generated_relay == 1)); then
  printf 'Generated a new Sentry Relay credential set with the pinned Relay image; values not printed.\n'
else
  printf 'Restored/preserved the existing Sentry Relay credential set without printing it.\n'
fi

bash "${BASH_SOURCE[0]}" --check
printf 'NEXT: redeploy only Sentry, prove functional ingestion, then refresh/finalize canonical runtime files:\n'
printf '  sudo midclt call -j app.redeploy sentry\n'
printf '  sudo bash scripts/truenas/diagnose-sentry.sh --check\n'
printf '  sudo bash scripts/truenas/smoke-sentry-event.sh\n'
printf '  sudo bash scripts/truenas/bootstrap-repository-env-files.sh --restage sentry\n'
printf '  sudo bash scripts/truenas/bootstrap-repository-env-files.sh --finalize sentry\n'
