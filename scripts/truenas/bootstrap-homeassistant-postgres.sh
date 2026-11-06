#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/secrets.sh
source "${SCRIPT_DIR}/../lib/secrets.sh"

MODE="${1:---check}"
SECRETS_FILE="${HOMEASSISTANT_SECRETS_FILE:-/mnt/cpool/secrets/runtime/homeassistant/.env.secrets}"
EXPECTED_HOST="${HOMEASSISTANT_POSTGRES_HOST:-172.17.0.24}"
EXPECTED_PORT="${HOMEASSISTANT_POSTGRES_PORT:-5432}"
EXPECTED_DB="${HOMEASSISTANT_POSTGRES_DB:-homeassistant}"
EXPECTED_USER="${HOMEASSISTANT_POSTGRES_USER:-homeassistant}"

function fail {
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

secrets_assert_file "${SECRETS_FILE}" POSTGRES_PASSWORD ||
  fail "Home Assistant secret contract is not satisfied"
homeassistant_password="$(secrets_get_value "${SECRETS_FILE}" POSTGRES_PASSWORD)" ||
  fail "unable to read POSTGRES_PASSWORD from ${SECRETS_FILE}"
[[ -n "${homeassistant_password}" ]] ||
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
  HOMEASSISTANT_DB_PASSWORD="${homeassistant_password}" docker exec -i \
    -e HOMEASSISTANT_DB_PASSWORD \
    "${POSTGRES_CONTAINER}" \
    psql \
      --set=ON_ERROR_STOP=1 \
      -U "${POSTGRES_ADMIN}" \
      -d postgres <<'SQL'
\getenv homeassistant_password HOMEASSISTANT_DB_PASSWORD

SELECT format(
  'CREATE ROLE homeassistant LOGIN PASSWORD %L',
  :'homeassistant_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = 'homeassistant'
) \gexec

SELECT format(
  'ALTER ROLE homeassistant PASSWORD %L',
  :'homeassistant_password'
) \gexec

SELECT 'CREATE DATABASE homeassistant OWNER homeassistant'
WHERE NOT EXISTS (
  SELECT 1 FROM pg_database WHERE datname = 'homeassistant'
) \gexec

ALTER DATABASE homeassistant OWNER TO homeassistant;
SQL
fi

state="$(
  docker exec "${POSTGRES_CONTAINER}"     psql -U "${POSTGRES_ADMIN}" -d postgres -Atc "
      SELECT
        (SELECT count(*) FROM pg_roles WHERE rolname='homeassistant')::text
        || '|' ||
        (SELECT count(*) FROM pg_database WHERE datname='homeassistant')::text
        || '|' ||
        COALESCE((
          SELECT pg_get_userbyid(datdba)
          FROM pg_database
          WHERE datname='homeassistant'
        ), '');
    "
)"
[[ "${state}" == "1|1|homeassistant" ]] ||
  fail "shared PostgreSQL Home Assistant role/database not ready (state=${state})"

if ! PGPASSWORD="${homeassistant_password}" docker exec \
  -e PGPASSWORD \
  "${POSTGRES_CONTAINER}" \
  psql \
    --set=ON_ERROR_STOP=1 \
    -h 127.0.0.1 \
    -U "${EXPECTED_USER}" \
    -d "${EXPECTED_DB}" \
    -Atc 'SELECT 1' |
  grep -qx '1'; then
  fail "Home Assistant role cannot authenticate to the shared PostgreSQL database"
fi

printf '✅ shared PostgreSQL ready for Home Assistant: host=%s port=%s role=%s database=%s\n'   "${EXPECTED_HOST}" "${EXPECTED_PORT}" "${EXPECTED_USER}" "${EXPECTED_DB}"
