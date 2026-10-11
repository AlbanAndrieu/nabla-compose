#!/usr/bin/env bash
# Read-only verification of the optional PostgreSQL metrics exporter.
set -euo pipefail

HOST="${POSTGRES_EXPORTER_HOST:-172.17.0.24}"
PORT="${POSTGRES_EXPORTER_PORT:-9187}"
SECRET_FILE="${POSTGRES_EXPORTER_SECRET_FILE:-/mnt/cpool/postgres/.env.secrets}"
printf 'PostgreSQL exporter runtime check host=%s port=%s\n' "${HOST}" "${PORT}"

if [[ -s "${SECRET_FILE}" ]]; then
  echo 'PASS exporter secret file exists (contents not read)'
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
