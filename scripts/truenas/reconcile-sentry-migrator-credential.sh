#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

MODE="${1:---check}"
SECRET_FILE="${SENTRY_MIGRATOR_SECRET_FILE:-/mnt/cpool/sentry/.env.migrator.secrets}"
CLICKHOUSE_CONTAINER="${SENTRY_CLICKHOUSE_CONTAINER:-ix-sentry-clickhouse-sentry-clickhouse-1}"
DIAG="${SCRIPT_DIR}/diagnose-sentry-migrator-credential.sh"

case "${MODE}" in
  --check)
    exec bash "${DIAG}"
    ;;
  --apply) ;;
  -h | --help)
    printf 'usage: sudo bash scripts/truenas/reconcile-sentry-migrator-credential.sh [--check|--apply]\n'
    exit 0
    ;;
  *)
    fail "unknown mode: ${MODE}"
    ;;
esac

require_root "run as root on TrueNAS"
require_commands docker awk openssl install mktemp stat
[[ -x "${DIAG}" || -f "${DIAG}" ]] || fail "diagnostic helper missing: ${DIAG}"
docker inspect "${CLICKHOUSE_CONTAINER}" >/dev/null 2>&1 ||
  fail "ClickHouse container not found: ${CLICKHOUSE_CONTAINER}"

read_key() {
  local key="$1"
  [[ -f "${SECRET_FILE}" ]] || return 0
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

if [[ -n "${password}" &&
      "${password}" == "${readonly_password}" &&
      "${password}" == "${trace_password}" ]]; then
  printf 'Preserving existing internally-consistent Sentry migrator secret.\n'
else
  password="$(openssl rand -hex 32)"
  tmp="$(mktemp /mnt/cpool/sentry/.env.migrator.secrets.tmp.XXXXXX)"
  trap 'rm -f "${tmp}"' EXIT
  {
    printf 'CLICKHOUSE_PASSWORD=%s\n' "${password}"
    printf 'CLICKHOUSE_READONLY_PASSWORD=%s\n' "${password}"
    printf 'CLICKHOUSE_TRACE_PASSWORD=%s\n' "${password}"
  } >"${tmp}"
  install -o root -g root -m 600 "${tmp}" "${SECRET_FILE}"
  rm -f "${tmp}"
  trap - EXIT
  printf 'Generated a new internally-consistent Sentry migrator secret without printing it.\n'
fi

docker exec   -e NABLA_MIGRATOR_PASSWORD="${password}"   "${CLICKHOUSE_CONTAINER}"   sh -lc '
    set -eu
    clickhouse-client       --user "$CLICKHOUSE_USER"       --password "$CLICKHOUSE_PASSWORD"       --multiquery       --query "
        CREATE USER IF NOT EXISTS sentry_migrator
          IDENTIFIED WITH sha256_password BY '$NABLA_MIGRATOR_PASSWORD';
        ALTER USER sentry_migrator
          IDENTIFIED WITH sha256_password BY '$NABLA_MIGRATOR_PASSWORD';
        GRANT ALL ON sentry.* TO sentry_migrator;
        GRANT SELECT ON system.tables TO sentry_migrator;
        GRANT SELECT ON system.replicas TO sentry_migrator;
        GRANT SELECT ON system.columns TO sentry_migrator;
        GRANT CREATE WORKLOAD, DROP WORKLOAD ON *.* TO sentry_migrator;
      "
  '

unset password readonly_password trace_password
bash "${DIAG}"
ok "Sentry migrator credential reconciled; Sentry can now be restarted"
