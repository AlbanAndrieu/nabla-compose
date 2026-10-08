#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

MODE="${1:---check}"
LEGACY_FILE="${SENTRY_SECRET_FILE:-/mnt/cpool/sentry/.env.secrets}"
CANONICAL_FILE="${SENTRY_RUNTIME_SECRET_FILE:-/mnt/cpool/secrets/runtime/sentry/.env.secrets}"
CLICKHOUSE_CONTAINER="${SENTRY_CLICKHOUSE_CONTAINER:-ix-sentry-clickhouse-sentry-clickhouse-1}"
DIAG="${SCRIPT_DIR}/diagnose-sentry-runtime-clickhouse-credential.sh"
TIMEOUT_SECONDS="${SENTRY_RUNTIME_CLICKHOUSE_RECONCILE_TIMEOUT_SECONDS:-20}"

case "${MODE}" in
  --check)
    exec bash "${DIAG}"
    ;;
  --apply) ;;
  -h | --help)
    printf 'usage: sudo bash scripts/truenas/reconcile-sentry-runtime-clickhouse-credential.sh [--check|--apply]\n'
    exit 0
    ;;
  *)
    fail "unknown mode: ${MODE}"
    ;;
esac

require_root "run as root on TrueNAS"
require_commands awk docker install mktemp openssl stat timeout
[[ -f "${LEGACY_FILE}" ]] || fail "missing legacy Sentry runtime secret file: ${LEGACY_FILE}"
docker inspect "${CLICKHOUSE_CONTAINER}" >/dev/null 2>&1 ||
  fail "ClickHouse container not found: ${CLICKHOUSE_CONTAINER}"

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

triplet_state() {
  local file="$1" password readonly_password trace_password present=0

  password="$(read_key "${file}" CLICKHOUSE_PASSWORD)"
  readonly_password="$(read_key "${file}" CLICKHOUSE_READONLY_PASSWORD)"
  trace_password="$(read_key "${file}" CLICKHOUSE_TRACE_PASSWORD)"
  [[ -n "${password}" ]] && present=$((present + 1))
  [[ -n "${readonly_password}" ]] && present=$((present + 1))
  [[ -n "${trace_password}" ]] && present=$((present + 1))

  case "${present}" in
    0) printf 'missing\n' ;;
    3)
      if [[ "${password}" == "${readonly_password}" && "${password}" == "${trace_password}" ]]; then
        printf 'complete\n'
      else
        printf 'conflict\n'
      fi
      ;;
    *) printf 'partial\n' ;;
  esac
}

triplets_match() {
  local left="$1" right="$2"
  [[ "$(read_key "${left}" CLICKHOUSE_PASSWORD)" == "$(read_key "${right}" CLICKHOUSE_PASSWORD)" &&
     "$(read_key "${left}" CLICKHOUSE_READONLY_PASSWORD)" == "$(read_key "${right}" CLICKHOUSE_READONLY_PASSWORD)" &&
     "$(read_key "${left}" CLICKHOUSE_TRACE_PASSWORD)" == "$(read_key "${right}" CLICKHOUSE_TRACE_PASSWORD)" ]]
}

write_triplet() {
  local file="$1" password="$2" tmp
  install -d -o root -g root -m 0700 "$(dirname "${file}")"
  tmp="$(mktemp "$(dirname "${file}")/.sentry-clickhouse-secret.tmp.XXXXXX")"
  trap 'rm -f "${tmp:-}"' RETURN

  if [[ -f "${file}" ]]; then
    awk -F= '
      $1 != "CLICKHOUSE_PASSWORD" &&
      $1 != "CLICKHOUSE_READONLY_PASSWORD" &&
      $1 != "CLICKHOUSE_TRACE_PASSWORD" { print }
    ' "${file}" >"${tmp}"
  fi
  printf 'CLICKHOUSE_PASSWORD=%s\n' "${password}" >>"${tmp}"
  printf 'CLICKHOUSE_READONLY_PASSWORD=%s\n' "${password}" >>"${tmp}"
  printf 'CLICKHOUSE_TRACE_PASSWORD=%s\n' "${password}" >>"${tmp}"
  install -o root -g root -m 0600 "${tmp}" "${file}"
  rm -f "${tmp}"
  trap - RETURN
}

legacy_state="$(triplet_state "${LEGACY_FILE}")"
canonical_state="$(triplet_state "${CANONICAL_FILE}")"

for pair in "legacy:${legacy_state}" "canonical:${canonical_state}"; do
  label="${pair%%:*}"
  state="${pair#*:}"
  case "${state}" in
    missing | complete) ;;
    partial | conflict)
      fail "${label} Sentry ClickHouse runtime password triplet is ${state}; refusing automatic replacement"
      ;;
  esac
done

if [[ "${legacy_state}" == "complete" && "${canonical_state}" == "complete" ]] &&
  ! triplets_match "${LEGACY_FILE}" "${CANONICAL_FILE}"; then
  fail "legacy and canonical Sentry ClickHouse runtime credentials conflict; refusing automatic rotation"
fi

generated=0
if [[ "${legacy_state}" == "complete" ]]; then
  password="$(read_key "${LEGACY_FILE}" CLICKHOUSE_PASSWORD)"
elif [[ "${canonical_state}" == "complete" ]]; then
  password="$(read_key "${CANONICAL_FILE}" CLICKHOUSE_PASSWORD)"
else
  password="$(openssl rand -hex 32)"
  generated=1
fi

[[ "${password}" =~ ^[0-9a-fA-F]{64}$ ]] ||
  fail "accepted Sentry runtime ClickHouse password is not the required 64-hex format; refusing implicit rotation"

# Keep both paths byte-compatible before any ClickHouse identity mutation so a
# later --restage cannot overwrite the accepted value.
write_triplet "${LEGACY_FILE}" "${password}"
write_triplet "${CANONICAL_FILE}" "${password}"

if ! timeout "${TIMEOUT_SECONDS}" docker exec "${CLICKHOUSE_CONTAINER}" sh -lc '
  clickhouse-client     --user "$CLICKHOUSE_USER"     --password "$CLICKHOUSE_PASSWORD"     --query "SELECT 1" >/dev/null
'; then
  fail "ClickHouse admin identity from the dedicated container cannot authenticate; refusing runtime-user mutation"
fi
ok "ClickHouse admin identity is usable"

{
  printf "CREATE USER IF NOT EXISTS sentry IDENTIFIED WITH sha256_password BY '%s';\n" "${password}"
  printf "ALTER USER sentry IDENTIFIED WITH sha256_password BY '%s';\n" "${password}"
  printf '%s\n'     'GRANT SELECT, INSERT, ALTER UPDATE, ALTER DELETE ON sentry.* TO sentry;'     'GRANT SELECT ON system.tables TO sentry;'
} |
  timeout "${TIMEOUT_SECONDS}" docker exec -i "${CLICKHOUSE_CONTAINER}" sh -lc '
    set -eu
    clickhouse-client       --user "$CLICKHOUSE_USER"       --password "$CLICKHOUSE_PASSWORD"       --multiquery
  '

if ((generated == 1)); then
  printf 'Generated the previously-missing Sentry runtime ClickHouse credential once; value not printed.\n'
else
  printf 'Preserved the accepted Sentry runtime ClickHouse credential; value not printed.\n'
fi

unset password
bash "${DIAG}"
ok "Sentry runtime ClickHouse identity and both runtime materializations are reconciled"
