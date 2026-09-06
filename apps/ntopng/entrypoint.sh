#!/bin/sh
set -eu

: "${CLICKHOUSE_HOST:=172.17.0.24}"
: "${NTOPNG_CLICKHOUSE_PASSWORD:?NTOPNG_CLICKHOUSE_PASSWORD must be set}"

NTOPNG_CLICKHOUSE_DATABASE="ntopng"
NTOPNG_CLICKHOUSE_USER="ntopng"
export NTOPNG_CLICKHOUSE_DATABASE NTOPNG_CLICKHOUSE_USER

case "${NTOPNG_CLICKHOUSE_PASSWORD}" in
  clickhouse|default)
    printf '%s\n' "Refusing insecure shared/default ClickHouse password for ntopng" >&2
    exit 1
    ;;
esac

# The upstream ntop image entrypoint (/run.sh) appends $NTOP_CONFIG to the
# ntopng command. Build the -F argument at runtime so the password comes from
# the container env_file rather than Compose interpolation or the repository.
export NTOP_CONFIG="-F clickhouse;${CLICKHOUSE_HOST};${NTOPNG_CLICKHOUSE_DATABASE};${NTOPNG_CLICKHOUSE_USER};${NTOPNG_CLICKHOUSE_PASSWORD}"

exec /run.sh "$@"
