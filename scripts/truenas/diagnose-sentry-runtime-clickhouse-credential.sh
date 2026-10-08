#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

SECRET_FILE="${SENTRY_RUNTIME_SECRET_FILE:-/mnt/cpool/secrets/runtime/sentry/.env.secrets}"
CLICKHOUSE_CONTAINER="${SENTRY_CLICKHOUSE_CONTAINER:-ix-sentry-clickhouse-sentry-clickhouse-1}"
TIMEOUT_SECONDS="${SENTRY_RUNTIME_CLICKHOUSE_CHECK_TIMEOUT_SECONDS:-15}"

require_root "run as root on TrueNAS"
require_commands docker awk stat timeout

[[ -f "${SECRET_FILE}" ]] || fail "missing Sentry runtime secret file: ${SECRET_FILE}"
[[ "$(stat -c '%a' "${SECRET_FILE}")" == "600" ]] ||
  fail "${SECRET_FILE} must be mode 0600"
docker inspect "${CLICKHOUSE_CONTAINER}" >/dev/null 2>&1 ||
  fail "ClickHouse container not found: ${CLICKHOUSE_CONTAINER}"

read_key() {
  local key="$1"
  awk -F= -v key="${key}" '
    $1 == key {
      sub(/^[^=]*=/, "")
      print
      exit
    }
  ' "${SECRET_FILE}"
}

password="$(read_key CLICKHOUSE_PASSWORD)"
readonly_password="$(read_key CLICKHOUSE_READONLY_PASSWORD)"
trace_password="$(read_key CLICKHOUSE_TRACE_PASSWORD)"

[[ -n "${password}" ]] || fail "CLICKHOUSE_PASSWORD is missing/empty"
[[ -n "${readonly_password}" ]] || fail "CLICKHOUSE_READONLY_PASSWORD is missing/empty"
[[ -n "${trace_password}" ]] || fail "CLICKHOUSE_TRACE_PASSWORD is missing/empty"
if ! [[ "${password}" == "${readonly_password}" && "${password}" == "${trace_password}" ]]; then
  fail "the three runtime ClickHouse passwords differ although all three roles use sentry"
fi
ok "Sentry runtime ClickHouse password triplet is present and internally consistent"

# shellcheck disable=SC2016
if ! timeout "${TIMEOUT_SECONDS}" docker exec "${CLICKHOUSE_CONTAINER}" sh -lc '
  clickhouse-client     --user "$CLICKHOUSE_USER"     --password "$CLICKHOUSE_PASSWORD"     --query "SELECT 1" >/dev/null
'; then
  fail "ClickHouse admin identity from the dedicated container cannot authenticate"
fi
ok "ClickHouse admin identity is usable"

user_count="$(
  printf "%s\n" "SELECT count() FROM system.users WHERE name = 'sentry';" |
    timeout "${TIMEOUT_SECONDS}" docker exec -i "${CLICKHOUSE_CONTAINER}" sh -lc '
      clickhouse-client         --user "$CLICKHOUSE_USER"         --password "$CLICKHOUSE_PASSWORD"         --format TabSeparatedRaw
    '
)"
[[ "${user_count}" == "1" ]] || fail "ClickHouse runtime user sentry is absent"
ok "ClickHouse runtime user sentry exists"

# shellcheck disable=SC2016
if ! timeout "${TIMEOUT_SECONDS}" docker exec   -e NABLA_SENTRY_CLICKHOUSE_PASSWORD="${password}"   "${CLICKHOUSE_CONTAINER}" sh -lc '
    clickhouse-client       --user sentry       --password "$NABLA_SENTRY_CLICKHOUSE_PASSWORD"       --database sentry       --query "SELECT 1" >/dev/null
  '; then
  fail "ClickHouse runtime user sentry rejects the canonical Sentry runtime password"
fi
ok "ClickHouse runtime user sentry accepts the canonical Sentry runtime password"

unset password readonly_password trace_password
