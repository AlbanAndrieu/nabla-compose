#!/usr/bin/env bash
# Provision the read-only PostgreSQL role used by the Databasus backup App
# (TrueNAS App `databasus`, outside this repository) on the shared PostgreSQL.
# --check (default) only verifies; --apply creates/updates the role and grants
# CONNECT on the listed databases. The role is LOGIN NOREPLICATION and a member
# of pg_read_all_data: enough for logical (pg_dump) backups, deliberately not
# for physical/WAL backups, which would need REPLICATION. The password comes
# from a 0600 secret file and is never printed or passed on a command line.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/secrets.sh
source "${SCRIPT_DIR}/../lib/secrets.sh"

MODE="${1:---check}"
SECRETS_FILE="${DATABASUS_SECRETS_FILE:-/mnt/cpool/secrets/runtime/databasus/.env.secrets}"
BACKUP_ROLE="${DATABASUS_POSTGRES_USER:-databasus}"
# Space-separated databases Databasus may dump from the shared instance.
BACKUP_DATABASES="${DATABASUS_BACKUP_DATABASES:-homeassistant keycloak joplin}"

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
[[ "${BACKUP_ROLE}" =~ ^[a-z][a-z0-9_]{0,62}$ ]] || fail "invalid role name"
for database in ${BACKUP_DATABASES}; do
  [[ "${database}" =~ ^[a-z][a-z0-9_]{0,62}$ ]] || fail "invalid database name: ${database}"
done

secrets_assert_file "${SECRETS_FILE}" POSTGRES_PASSWORD ||
  fail "Databasus secret contract is not satisfied"
backup_password="$(secrets_get_value "${SECRETS_FILE}" POSTGRES_PASSWORD)" ||
  fail "unable to read POSTGRES_PASSWORD from ${SECRETS_FILE}"
[[ -n "${backup_password}" ]] ||
  fail "${SECRETS_FILE} must define non-empty POSTGRES_PASSWORD"

POSTGRES_CONTAINER="$(
  docker ps --filter 'label=com.docker.compose.project=ix-postgres' \
    --filter 'label=com.docker.compose.service=postgres' \
    --format '{{.Names}}' | head -1
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
  docker exec "${POSTGRES_CONTAINER}" sh -lc 'printf "%s" "${POSTGRES_USER:-postgres}"'
)"
[[ -n "${POSTGRES_ADMIN}" ]] ||
  fail "shared PostgreSQL administrative role could not be determined"

for database in ${BACKUP_DATABASES}; do
  exists="$(docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_ADMIN}" -d postgres -Atc \
    "SELECT count(*) FROM pg_database WHERE datname='${database}'")"
  [[ "${exists}" == "1" ]] || fail "database ${database} does not exist yet; bootstrap it first"
done

if [[ "${MODE}" == "--apply" ]]; then
  DATABASUS_DB_PASSWORD="${backup_password}" DATABASUS_ROLE="${BACKUP_ROLE}" \
    DATABASUS_DATABASES="${BACKUP_DATABASES}" docker exec -i \
    -e DATABASUS_DB_PASSWORD -e DATABASUS_ROLE -e DATABASUS_DATABASES \
    "${POSTGRES_CONTAINER}" \
    psql \
      --set=ON_ERROR_STOP=1 \
      -U "${POSTGRES_ADMIN}" \
      -d postgres <<'SQL'
\getenv backup_password DATABASUS_DB_PASSWORD
\getenv backup_role DATABASUS_ROLE
\getenv backup_databases DATABASUS_DATABASES

SELECT format('CREATE ROLE %I LOGIN NOREPLICATION NOCREATEDB NOCREATEROLE PASSWORD %L',
              :'backup_role', :'backup_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'backup_role') \gexec

SELECT format('ALTER ROLE %I NOREPLICATION NOCREATEDB NOCREATEROLE NOSUPERUSER PASSWORD %L',
              :'backup_role', :'backup_password') \gexec

SELECT format('GRANT pg_read_all_data TO %I', :'backup_role') \gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO %I', d, :'backup_role')
FROM regexp_split_to_table(:'backup_databases', '\s+') AS d
WHERE d <> '' \gexec
SQL
fi

state="$(
  docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_ADMIN}" -d postgres -Atc "
    SELECT
      (SELECT count(*) FROM pg_roles WHERE rolname='${BACKUP_ROLE}' AND NOT rolsuper AND NOT rolreplication)::text
      || '|' ||
      (SELECT count(*) FROM pg_auth_members m
         JOIN pg_roles r ON r.oid = m.roleid
         JOIN pg_roles u ON u.oid = m.member
       WHERE r.rolname='pg_read_all_data' AND u.rolname='${BACKUP_ROLE}')::text;
  "
)"
[[ "${state}" == "1|1" ]] ||
  fail "backup role ${BACKUP_ROLE} not ready (state=${state}): expected LOGIN NOREPLICATION + pg_read_all_data"

for database in ${BACKUP_DATABASES}; do
  if ! PGPASSWORD="${backup_password}" docker exec -e PGPASSWORD "${POSTGRES_CONTAINER}" \
    psql --set=ON_ERROR_STOP=1 -h 127.0.0.1 -U "${BACKUP_ROLE}" -d "${database}" -Atc 'SELECT 1' |
    grep -qx '1'; then
    fail "backup role ${BACKUP_ROLE} cannot connect to database ${database}"
  fi
done

printf '✅ shared PostgreSQL ready for Databasus: role=%s (read-only) databases=%s\n' \
  "${BACKUP_ROLE}" "${BACKUP_DATABASES}"
