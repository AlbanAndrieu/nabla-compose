#!/usr/bin/env bash
# Provision the read-only PostgreSQL role used by the versioned backup job
# (apps/postgresbackup) on the shared TrueNAS PostgreSQL.
# --check (default) only verifies; --apply creates/updates the role and grants
# CONNECT on the listed databases. The role is LOGIN NOREPLICATION and a member
# of pg_read_all_data: enough for logical (pg_dump) backups, deliberately not
# for physical/WAL backups, which would need REPLICATION. The password comes
# from a 0600 secret file and is never printed or passed on a command line.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"
# shellcheck source=../lib/secrets.sh
source "${SCRIPT_DIR}/../lib/secrets.sh"
# shellcheck source=../lib/postgres.sh
source "${SCRIPT_DIR}/../lib/postgres.sh"

MODE="${1:---check}"
SECRETS_FILE="${POSTGRES_BACKUP_SECRETS_FILE:-/mnt/cpool/secrets/runtime/postgresbackup/.env.secrets}"
BACKUP_ROLE="${POSTGRES_BACKUP_USER:-pgbackup}"
# Space-separated databases the job may dump (keep in sync with apps/postgresbackup/compose.yml).
BACKUP_DATABASES="${POSTGRES_BACKUP_DATABASES:-keycloak joplin homeassistant netbox dependencytrack scanopy jobs defectdojo langfuse n8n sonarqube fastapisample}"
# Databases dumped only by the monthly/yearly archive jobs
# (scripts/truenas/reconcile-postgresbackup-cron.py); they also need CONNECT.
ARCHIVE_DATABASES="${POSTGRES_BACKUP_ARCHIVE_DATABASES:-sentry}"
BACKUP_DATABASES="${BACKUP_DATABASES} ${ARCHIVE_DATABASES}"

case "${MODE}" in
--check | --apply) ;;
*) fail "usage: $0 [--check|--apply]" ;;
esac

require_root "run with sudo so the shared PostgreSQL container can be inspected"
require_commands docker grep head python3 stat
postgres_identifier_valid "${BACKUP_ROLE}" || fail "invalid role name"
for database in ${BACKUP_DATABASES}; do
  postgres_identifier_valid "${database}" || fail "invalid database name: ${database}"
done

secrets_assert_file "${SECRETS_FILE}" POSTGRES_PASSWORD ||
  fail "postgresbackup secret contract is not satisfied"
backup_password="$(secrets_get_value "${SECRETS_FILE}" POSTGRES_PASSWORD)" ||
  fail "unable to read POSTGRES_PASSWORD from ${SECRETS_FILE}"
[[ -n "${backup_password}" ]] ||
  fail "${SECRETS_FILE} must define non-empty POSTGRES_PASSWORD"

POSTGRES_CONTAINER="$(postgres_shared_container)" || exit 1
POSTGRES_ADMIN="$(postgres_admin_role "${POSTGRES_CONTAINER}")" || exit 1

# Staged rollout: databases that are not created yet are skipped with a warning
# (re-run after their bootstrap); set POSTGRES_BACKUP_REQUIRE_ALL=true to fail.
present_databases=""
for database in ${BACKUP_DATABASES}; do
  if postgres_database_exists "${POSTGRES_CONTAINER}" "${POSTGRES_ADMIN}" "${database}"; then
    present_databases="${present_databases} ${database}"
  elif [[ "${POSTGRES_BACKUP_REQUIRE_ALL:-false}" == "true" ]]; then
    fail "database ${database} does not exist yet; bootstrap it first"
  else
    warn "database ${database} does not exist yet; skipped (re-run after its bootstrap)"
  fi
done
BACKUP_DATABASES="${present_databases# }"
[[ -n "${BACKUP_DATABASES}" ]] || fail "none of the configured databases exist yet"

if [[ "${MODE}" == "--apply" ]]; then
  PGBACKUP_DB_PASSWORD="${backup_password}" PGBACKUP_ROLE="${BACKUP_ROLE}" \
    PGBACKUP_DATABASES="${BACKUP_DATABASES}" docker exec -i \
    -e PGBACKUP_DB_PASSWORD -e PGBACKUP_ROLE -e PGBACKUP_DATABASES \
    "${POSTGRES_CONTAINER}" \
    psql \
    --set=ON_ERROR_STOP=1 \
    -U "${POSTGRES_ADMIN}" \
    -d postgres <<'SQL'
\getenv backup_password PGBACKUP_DB_PASSWORD
\getenv backup_role PGBACKUP_ROLE
\getenv backup_databases PGBACKUP_DATABASES

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
  postgres_admin_query "${POSTGRES_CONTAINER}" "${POSTGRES_ADMIN}" "
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
  PGPASSWORD="${backup_password}" postgres_assert_login "${POSTGRES_CONTAINER}" "${BACKUP_ROLE}" "${database}" ||
    fail "backup role ${BACKUP_ROLE} cannot connect to database ${database}"
done
unset backup_password

ok "shared PostgreSQL ready for postgresbackup: role=${BACKUP_ROLE} (read-only) databases=${BACKUP_DATABASES}"
