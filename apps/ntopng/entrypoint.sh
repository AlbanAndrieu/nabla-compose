#!/bin/sh
set -eu

: "${CLICKHOUSE_HOST:=172.17.0.24}"
: "${NTOPNG_INTERFACE:=eth0}"
: "${NTOPNG_HTTP_PORT:=3000}"

secret_file="/run/secrets/ntopng_runtime_env"
if [ ! -r "${secret_file}" ]; then
  printf '%s\n' "ntopng runtime secret file is missing or unreadable" >&2
  exit 1
fi

NTOPNG_CLICKHOUSE_PASSWORD="$(
  sed -n 's/^NTOPNG_CLICKHOUSE_PASSWORD=//p' "${secret_file}" |
    tail -n 1
)"

# Vaultwarden rendering quotes dotenv values literally. Strip only matching
# outer quotes, then keep the credential format deliberately narrow so no
# general-purpose dotenv evaluation is required here.
case "${NTOPNG_CLICKHOUSE_PASSWORD}" in
  \'*\')
    NTOPNG_CLICKHOUSE_PASSWORD=${NTOPNG_CLICKHOUSE_PASSWORD#\'}
    NTOPNG_CLICKHOUSE_PASSWORD=${NTOPNG_CLICKHOUSE_PASSWORD%\'}
    ;;
  \"*\")
    NTOPNG_CLICKHOUSE_PASSWORD=${NTOPNG_CLICKHOUSE_PASSWORD#\"}
    NTOPNG_CLICKHOUSE_PASSWORD=${NTOPNG_CLICKHOUSE_PASSWORD%\"}
    ;;
esac

if [ "${#NTOPNG_CLICKHOUSE_PASSWORD}" -ne 64 ]; then
  printf '%s\n' "NTOPNG_CLICKHOUSE_PASSWORD must be exactly 64 hexadecimal characters" >&2
  exit 1
fi

case "${NTOPNG_CLICKHOUSE_PASSWORD}" in
  *[!0-9A-Fa-f]*)
    printf '%s\n' "NTOPNG_CLICKHOUSE_PASSWORD must be exactly 64 hexadecimal characters" >&2
    exit 1
    ;;
esac

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
# environment before delegating to the upstream image entrypoint. The source
# credential file is mounted as a Compose secret, not injected into Config.Env.
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
