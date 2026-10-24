#!/usr/bin/env bash
# Read-only verification of the optional PostgreSQL metrics exporter.
set -euo pipefail

HOST="${POSTGRES_EXPORTER_HOST:-172.17.0.24}"
PORT="${POSTGRES_EXPORTER_PORT:-9187}"
# Only use the dedicated Vaultwarden materialization for this exporter.
# Do not fall back to the database's privileged application secrets.
SECRET_FILE="${POSTGRES_EXPORTER_SECRET_FILE:-/mnt/cpool/secrets/runtime/postgres-exporter/.env.secrets}"
printf 'PostgreSQL exporter runtime check host=%s port=%s\n' "${HOST}" "${PORT}"

if [[ -s "${SECRET_FILE}" && ! -L "${SECRET_FILE}" ]]; then
  if grep -Eq '^[[:space:]]*DATA_SOURCE_NAME=[^[:space:]]' "${SECRET_FILE}"; then
    echo 'PASS exporter DATA_SOURCE_NAME present (value hidden)'
  else
    echo 'WARN exporter file is missing DATA_SOURCE_NAME'
  fi
  if [[ "$(stat -c '%u:%g:%a' -- "${SECRET_FILE}")" == '0:0:600' ]]; then
    echo 'PASS runtime secret metadata root:root mode 600'
  else
    echo 'WARN runtime secret owner/mode is not root:root 600'
  fi
else
  echo 'WARN exporter secret absent/empty/invalid; provision before deployment'
fi

if ! command -v docker >/dev/null; then
  echo 'WARN docker unavailable'
  exit 2
fi

# Avoid relying on a container name: the active TrueNAS project uses ix- prefixes.
matches="$(docker ps -a --format '{{.Names}} {{.Status}}' |
  grep -Ei '(^|[-_])postgres[-_]exporter([-_ ]|$)' || true)"
if [[ -z "${matches}" ]]; then
  echo 'WARN postgres-exporter is not deployed; PostgreSQL itself may be healthy'
  exit 2
fi
printf 'exporter_containers=%s\n' "${matches}"
if ! curl --silent --show-error --fail --max-time 5 --output /dev/null "http://${HOST}:${PORT}/metrics"; then
  echo 'FAIL postgres-exporter /metrics unavailable'
  exit 1
fi
echo 'PASS postgres-exporter metrics endpoint reachable'
