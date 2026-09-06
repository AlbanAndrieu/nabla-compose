#!/bin/sh
set -eu

: "${CLICKHOUSE_HOST:=172.17.0.24}"
: "${NTOPNG_INTERFACE:=eth0}"
: "${NTOPNG_HTTP_PORT:=3000}"
: "${NTOPNG_CLICKHOUSE_PASSWORD:?NTOPNG_CLICKHOUSE_PASSWORD must be set}"

NTOPNG_CLICKHOUSE_DATABASE="ntopng"
NTOPNG_CLICKHOUSE_USER="ntopng"

case "${NTOPNG_CLICKHOUSE_PASSWORD}" in
  clickhouse|default)
    printf '%s\n' "Refusing insecure shared/default ClickHouse password for ntopng" >&2
    exit 1
    ;;
esac

# ntopng accepts a configuration file as its single argument. Generate it at
# runtime so the ClickHouse password is neither stored in the repository nor
# exposed in the ntopng process argv. The secret is removed from the inherited
# environment before delegating to the upstream image entrypoint.
config="/run/nabla-ntopng.conf"
umask 077
cat >"${config}" <<EOF
--interface=${NTOPNG_INTERFACE}
--http-port=${NTOPNG_HTTP_PORT}
--dump-flows=clickhouse;${CLICKHOUSE_HOST};${NTOPNG_CLICKHOUSE_DATABASE};${NTOPNG_CLICKHOUSE_USER};${NTOPNG_CLICKHOUSE_PASSWORD}
--strict-startup=
EOF
chmod 600 "${config}"

unset NTOP_CONFIG NTOPNG_CLICKHOUSE_PASSWORD
exec /run.sh "${config}"
