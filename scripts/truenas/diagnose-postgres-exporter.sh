#!/usr/bin/env bash
# Read-only verification of the optional PostgreSQL metrics exporter.
set -euo pipefail

HOST="${POSTGRES_EXPORTER_HOST:-172.17.0.24}"
PORT="${POSTGRES_EXPORTER_PORT:-9187}"
# Prefer an existing centrally materialized runtime secret; never print values.
SECRET_FILE="${POSTGRES_EXPORTER_SECRET_FILE:-}"
if [[ -z "${SECRET_FILE}" ]]; then
  for candidate in \
    /mnt/cpool/secrets/runtime/postgres-exporter/.env.secrets \
    /mnt/cpool/secrets/runtime/postgres/.env.secrets \
    /mnt/cpool/postgres/.env.secrets; do
    if [[ -s "${candidate}" ]]; then SECRET_FILE="${candidate}"; break; fi
  done
fi
SECRET_FILE="${SECRET_FILE:-/mnt/cpool/secrets/runtime/postgres-exporter/.env.secrets}"
printf 'PostgreSQL exporter runtime check host=%s port=%s\n' "${HOST}" "${PORT}"

if [[ -s "${SECRET_FILE}" ]]; then
  if grep -Eq '^[[:space:]]*(export[[:space:]]+)?POSTGRES_EXPORTER_DSN=' "${SECRET_FILE}"; then
    printf 'PASS exporter DSN key is materialized at %s (value hidden)\n' "${SECRET_FILE}"
  else
    echo 'WARN runtime file exists but POSTGRES_EXPORTER_DSN is not declared'
  fi
else
  echo 'WARN exporter secret file absent or empty; do not deploy until provisioned'
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
