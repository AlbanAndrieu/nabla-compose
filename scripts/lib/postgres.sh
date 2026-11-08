# shellcheck shell=bash
# Shared helpers for the shared TrueNAS PostgreSQL App (`postgres`).
#
# Read-only when sourced. Only postgres_ensure_role_database mutates the
# server, and only when a caller invokes it explicitly. Passwords travel
# through the environment of `docker exec -e NAME` (never argv, never printed).

postgres_fail() {
  printf 'ERROR: %s\n' "$*" >&2
  return 1
}

# PostgreSQL identifiers created by this repository: lowercase, no quoting needed.
postgres_identifier_valid() {
  [[ "${1:-}" =~ ^[a-z][a-z0-9_]{0,62}$ ]]
}

# Resolve the shared PostgreSQL container: the Compose label is authoritative,
# the historical ix-postgres-postgres-N name is the fallback.
postgres_shared_container() {
  local name="${NABLA_POSTGRES_CONTAINER:-}"
  if [[ -z "${name}" ]]; then
    name="$(
      docker ps \
        --filter 'label=com.docker.compose.project=ix-postgres' \
        --filter 'label=com.docker.compose.service=postgres' \
        --format '{{.Names}}' | head -1
    )"
  fi
  if [[ -z "${name}" ]]; then
    name="$(
      docker ps --format '{{.Names}}' |
        grep -E '^ix-postgres-postgres-[0-9]+$' |
        head -1 || true
    )"
  fi
  [[ -n "${name}" ]] || postgres_fail "shared TrueNAS PostgreSQL container not found" || return 1
  printf '%s\n' "${name}"
}

postgres_admin_role() {
  local container="${1:?PostgreSQL container is required}"
  local role
  role="$(docker exec "${container}" sh -lc 'printf "%s" "${POSTGRES_USER:-postgres}"')"
  [[ -n "${role}" ]] ||
    postgres_fail "shared PostgreSQL administrative role could not be determined" || return 1
  printf '%s\n' "${role}"
}

# Run one read-only SQL statement as the administrative role (tuples only).
postgres_admin_query() {
  local container="${1:?PostgreSQL container is required}"
  local admin="${2:?PostgreSQL admin role is required}"
  local sql="${3:?SQL is required}"
  docker exec "${container}" psql --set=ON_ERROR_STOP=1 -U "${admin}" -d postgres -Atc "${sql}"
}

postgres_database_exists() {
  local container="${1:?}" admin="${2:?}" database="${3:?database is required}"
  postgres_identifier_valid "${database}" || postgres_fail "invalid database name: ${database}" || return 2
  [[ "$(postgres_admin_query "${container}" "${admin}" \
    "SELECT count(*) FROM pg_database WHERE datname='${database}'")" == "1" ]]
}

# "<role count>|<database count>|<database owner>", e.g. "1|1|joplin".
postgres_role_database_state() {
  local container="${1:?}" admin="${2:?}" role="${3:?role is required}" database="${4:?database is required}"
  postgres_identifier_valid "${role}" || postgres_fail "invalid role name: ${role}" || return 2
  postgres_identifier_valid "${database}" || postgres_fail "invalid database name: ${database}" || return 2
  postgres_admin_query "${container}" "${admin}" "
    SELECT
      (SELECT count(*) FROM pg_roles WHERE rolname='${role}')::text
      || '|' ||
      (SELECT count(*) FROM pg_database WHERE datname='${database}')::text
      || '|' ||
      COALESCE((SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='${database}'), '');
  "
}

# Idempotent role + database provisioning. The password is read from the
# NABLA_DB_PASSWORD variable of the caller's environment:
#   NABLA_DB_PASSWORD="${secret}" postgres_ensure_role_database "${c}" "${admin}" joplin joplin
postgres_ensure_role_database() {
  local container="${1:?}" admin="${2:?}" role="${3:?role is required}" database="${4:?database is required}"
  postgres_identifier_valid "${role}" || postgres_fail "invalid role name: ${role}" || return 2
  postgres_identifier_valid "${database}" || postgres_fail "invalid database name: ${database}" || return 2
  [[ -n "${NABLA_DB_PASSWORD:-}" ]] || postgres_fail "NABLA_DB_PASSWORD must be set in the environment" || return 2
  NABLA_DB_PASSWORD="${NABLA_DB_PASSWORD}" docker exec -i \
    -e NABLA_DB_PASSWORD \
    -e NABLA_DB_USER="${role}" \
    -e NABLA_DB_NAME="${database}" \
    "${container}" \
    psql --set=ON_ERROR_STOP=1 -U "${admin}" -d postgres <<'SQL'
\getenv target_password NABLA_DB_PASSWORD
\getenv target_user NABLA_DB_USER
\getenv target_db NABLA_DB_NAME

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'target_user', :'target_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'target_user') \gexec

SELECT format('ALTER ROLE %I PASSWORD %L', :'target_user', :'target_password') \gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'target_db', :'target_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'target_db') \gexec

SELECT format('ALTER DATABASE %I OWNER TO %I', :'target_db', :'target_user') \gexec
SQL
}

# Prove that a role can authenticate over TCP to its database. The password is
# read from PGPASSWORD in the caller's environment:
#   PGPASSWORD="${secret}" postgres_assert_login "${c}" joplin joplin
postgres_assert_login() {
  local container="${1:?}" role="${2:?role is required}" database="${3:?database is required}"
  [[ -n "${PGPASSWORD:-}" ]] || postgres_fail "PGPASSWORD must be set in the environment" || return 2
  PGPASSWORD="${PGPASSWORD}" docker exec -e PGPASSWORD "${container}" \
    psql --set=ON_ERROR_STOP=1 -h 127.0.0.1 -U "${role}" -d "${database}" -Atc 'SELECT 1' |
    grep -qx '1'
}

# Print one component (user|password|host|port|database) of a postgres:// URL
# read from the NABLA_DB_URL environment variable; the URL never reaches argv.
postgres_url_component() {
  local component="${1:?component is required}"
  case "${component}" in
  user | password | host | port | database) ;;
  *) postgres_fail "unknown URL component: ${component}" || return 2 ;;
  esac
  [[ -n "${NABLA_DB_URL:-}" ]] || postgres_fail "NABLA_DB_URL must be set in the environment" || return 2
  NABLA_DB_URL="${NABLA_DB_URL}" python3 - "${component}" <<'PY'
import os
import sys
from urllib.parse import unquote, urlsplit

parsed = urlsplit(os.environ["NABLA_DB_URL"])
if parsed.scheme not in {"postgres", "postgresql"}:
    raise SystemExit("database URL must use the postgres/postgresql scheme")
database = parsed.path.lstrip("/")
values = {
    "user": unquote(parsed.username or ""),
    "password": unquote(parsed.password or ""),
    "host": parsed.hostname or "",
    "port": str(parsed.port or 5432),
    "database": database,
}
sys.stdout.write(values[sys.argv[1]])
PY
}
