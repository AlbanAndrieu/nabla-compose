#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

MODE="${1:---check}"
SECRET_FILE="${SENTRY_RUNTIME_SECRET_FILE:-/mnt/cpool/secrets/runtime/sentry/.env.secrets}"
CLICKHOUSE_CONTAINER="${SENTRY_CLICKHOUSE_CONTAINER:-ix-sentry-clickhouse-sentry-clickhouse-1}"
DIAG="${SCRIPT_DIR}/diagnose-sentry-runtime-clickhouse-credential.sh"

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
require_commands docker awk stat
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
[[ "${password}" == "${readonly_password}" && "${password}" == "${trace_password}" ]] ||
  fail "runtime ClickHouse password triplet is inconsistent; refusing identity mutation"

if [[ "${#password}" -lt 16 || "${#password}" -gt 256 ]] ||
  [[ "${password}" == *$'\n'* || "${password}" == *$'\r'* ]]; then
  fail "runtime ClickHouse password has an unsafe format/length; refusing identity mutation"
fi

if ! docker exec "${CLICKHOUSE_CONTAINER}" sh -lc '
  clickhouse-client     --user "$CLICKHOUSE_USER"     --password "$CLICKHOUSE_PASSWORD"     --query "SELECT 1" >/dev/null
'; then
  fail "ClickHouse admin identity from the dedicated container cannot authenticate; refusing runtime-user mutation"
fi
ok "ClickHouse admin identity is usable"

sql_password="${password//\\/\\\\}"
sql_password="${sql_password//\'/\\\'}"

{
  printf "CREATE USER IF NOT EXISTS sentry IDENTIFIED WITH sha256_password BY '%s';\n" "${sql_password}"
  printf "ALTER USER sentry IDENTIFIED WITH sha256_password BY '%s';\n" "${sql_password}"
  printf '%s\n'     'GRANT SELECT, INSERT, ALTER UPDATE, ALTER DELETE ON sentry.* TO sentry;'     'GRANT SELECT ON system.tables TO sentry;'
} |
  docker exec -i "${CLICKHOUSE_CONTAINER}" sh -lc '
    set -eu
    clickhouse-client       --user "$CLICKHOUSE_USER"       --password "$CLICKHOUSE_PASSWORD"       --multiquery
  '

unset password readonly_password trace_password sql_password
bash "${DIAG}"
ok "Sentry runtime ClickHouse identity reconciled to the existing canonical secret without rotating it"
