#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
SECRETS_FILE="${JOPLIN_SECRETS_FILE:-/mnt/cpool/secrets/runtime/joplin/.env.secrets}"
EXPECTED_HOST="${JOPLIN_POSTGRES_HOST:-172.17.0.24}"
EXPECTED_PORT="${JOPLIN_POSTGRES_PORT:-5432}"
EXPECTED_DB="${JOPLIN_POSTGRES_DB:-joplin}"
EXPECTED_USER="${JOPLIN_POSTGRES_USER:-joplin}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: $0 [--check|--apply]" ;;
esac

[[ "${EUID}" -eq 0 ]] ||
  fail "run with sudo so the shared PostgreSQL container can be inspected"
for command in docker grep head python3 stat; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ -f "${SECRETS_FILE}" ]] || fail "missing Joplin secret file: ${SECRETS_FILE}"
metadata="$(stat -c '%U:%G %a' "${SECRETS_FILE}")"
[[ "${metadata}" == "root:root 600" ]] ||
  fail "${SECRETS_FILE} owner/mode=${metadata}; expected root:root 600"
[[ -s "${SECRETS_FILE}" ]] || fail "${SECRETS_FILE} is empty"

joplin_password="$(
  python3 - "${SECRETS_FILE}" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

path = Path(sys.argv[1])
value = ""
for raw_line in path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, raw_value = line.split("=", 1)
    if key != "POSTGRES_PASSWORD":
        continue
    raw_value = raw_value.strip()
    if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {"'", '"'}:
        raw_value = raw_value[1:-1]
    value = raw_value
    break
sys.stdout.write(value)
PY
)"
[[ -n "${joplin_password}" ]] ||
  fail "${SECRETS_FILE} must define non-empty POSTGRES_PASSWORD"

POSTGRES_CONTAINER="$(
  docker ps     --filter 'label=com.docker.compose.project=ix-postgres'     --filter 'label=com.docker.compose.service=postgres'     --format '{{.Names}}' |
    head -1
)"
if [[ -z "${POSTGRES_CONTAINER}" ]]; then
  POSTGRES_CONTAINER="$(
    docker ps --format '{{.Names}}' |
      grep -E '^ix-postgres-postgres-[0-9]+$' |
      head -1 || true
  )"
fi
[[ -n "${POSTGRES_CONTAINER}" ]] || fail "shared TrueNAS PostgreSQL container not found"

POSTGRES_ADMIN="$(
  docker exec "${POSTGRES_CONTAINER}"     sh -lc 'printf "%s" "${POSTGRES_USER:-postgres}"'
)"
[[ -n "${POSTGRES_ADMIN}" ]] ||
  fail "shared PostgreSQL administrative role could not be determined"

if [[ "${MODE}" == "--apply" ]]; then
  docker exec -i     -e JOPLIN_DB_PASSWORD="${joplin_password}"     "${POSTGRES_CONTAINER}"     psql       --set=ON_ERROR_STOP=1       -U "${POSTGRES_ADMIN}"       -d postgres <<'SQL'
\getenv joplin_password JOPLIN_DB_PASSWORD

SELECT format(
  'CREATE ROLE joplin LOGIN PASSWORD %L',
  :'joplin_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = 'joplin'
) \gexec

SELECT format(
  'ALTER ROLE joplin PASSWORD %L',
  :'joplin_password'
) \gexec

SELECT 'CREATE DATABASE joplin OWNER joplin'
WHERE NOT EXISTS (
  SELECT 1 FROM pg_database WHERE datname = 'joplin'
) \gexec

ALTER DATABASE joplin OWNER TO joplin;
SQL
fi

state="$(
  docker exec "${POSTGRES_CONTAINER}"     psql -U "${POSTGRES_ADMIN}" -d postgres -Atc "
      SELECT
        (SELECT count(*) FROM pg_roles WHERE rolname='joplin')::text
        || '|' ||
        (SELECT count(*) FROM pg_database WHERE datname='joplin')::text
        || '|' ||
        COALESCE((
          SELECT pg_get_userbyid(datdba)
          FROM pg_database
          WHERE datname='joplin'
        ), '');
    "
)"
[[ "${state}" == "1|1|joplin" ]] ||
  fail "shared PostgreSQL Joplin role/database not ready (state=${state})"

if ! docker exec   -e PGPASSWORD="${joplin_password}"   "${POSTGRES_CONTAINER}"   psql     --set=ON_ERROR_STOP=1     -h 127.0.0.1     -U "${EXPECTED_USER}"     -d "${EXPECTED_DB}"     -Atc 'SELECT 1' |
  grep -qx '1'; then
  fail "Joplin role cannot authenticate to the shared PostgreSQL database"
fi

printf '✅ shared PostgreSQL ready for Joplin: host=%s port=%s role=%s database=%s\n'   "${EXPECTED_HOST}" "${EXPECTED_PORT}" "${EXPECTED_USER}" "${EXPECTED_DB}"
