#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

SECRET_FILE="${SENTRY_MIGRATOR_SECRET_FILE:-/mnt/cpool/sentry/.env.migrator.secrets}"
CLICKHOUSE_CONTAINER="${SENTRY_CLICKHOUSE_CONTAINER:-ix-sentry-clickhouse-sentry-clickhouse-1}"
TIMEOUT_SECONDS="${SENTRY_MIGRATOR_CHECK_TIMEOUT_SECONDS:-15}"

require_root "run as root on TrueNAS"
require_commands docker awk stat timeout

[[ -f "${SECRET_FILE}" ]] || fail "missing migrator secret file: ${SECRET_FILE}"
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
ok "all three Sentry migrator ClickHouse secret keys are present"

if ! [[ "${password}" == "${readonly_password}" && "${password}" == "${trace_password}" ]]; then
  fail "the three migrator passwords differ although all three roles use sentry_migrator"
fi
ok "migrator ClickHouse passwords are internally consistent"

# shellcheck disable=SC2016 # Variables are intentionally expanded inside the container.
if ! timeout "${TIMEOUT_SECONDS}" docker exec "${CLICKHOUSE_CONTAINER}" sh -lc '
  clickhouse-client \
    --user "$CLICKHOUSE_USER" \
    --password "$CLICKHOUSE_PASSWORD" \
    --query "SELECT 1" >/dev/null
'; then
  fail "ClickHouse admin identity from the dedicated container cannot authenticate"
fi
ok "ClickHouse admin identity is usable"

# shellcheck disable=SC2016 # Variables are intentionally expanded inside the container.
user_count="$(
  printf "%s\n" "SELECT count() FROM system.users WHERE name = 'sentry_migrator';" |
    timeout "${TIMEOUT_SECONDS}" docker exec -i "${CLICKHOUSE_CONTAINER}" sh -lc '
      clickhouse-client \
        --user "$CLICKHOUSE_USER" \
        --password "$CLICKHOUSE_PASSWORD" \
        --format TabSeparatedRaw
    '
)"
[[ "${user_count}" == "1" ]] ||
  fail "ClickHouse user sentry_migrator is absent"
ok "ClickHouse user sentry_migrator exists"

# shellcheck disable=SC2016 # NABLA_MIGRATOR_PASSWORD is expanded inside the container.
if timeout "${TIMEOUT_SECONDS}" docker exec \
  -e NABLA_MIGRATOR_PASSWORD="${password}" \
  "${CLICKHOUSE_CONTAINER}" \
  sh -lc '
    clickhouse-client \
      --user sentry_migrator \
      --password "$NABLA_MIGRATOR_PASSWORD" \
      --query "SELECT 1" >/dev/null
  '; then
  ok "sentry_migrator accepts the current /mnt/cpool/sentry/.env.migrator.secrets password"
  exit 0
fi

fail "sentry_migrator rejects the current migrator secret; rotate/reconcile the ClickHouse identity before restarting Sentry"
