#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
APP="${2:-}"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: $0 [--check|--apply] <plumber|netbox|dependency-track|defectdojo>" ;;
esac

case "${APP}" in
  plumber)
    DB_USER="jobs"
    DB_NAME="jobs"
    SECRET_KEY="JOBS_DB_PASSWORD"
    ;;
  netbox)
    DB_USER="netbox"
    DB_NAME="netbox"
    SECRET_KEY="DB_PASSWORD"
    ;;
  dependency-track)
    DB_USER="dependencytrack"
    DB_NAME="dependencytrack"
    SECRET_KEY="ALPINE_DATABASE_PASSWORD"
    ;;
  defectdojo)
    DB_USER="defectdojo"
    DB_NAME="defectdojo"
    SECRET_KEY="DD_DATABASE_URL"
    ;;
  *) fail "unsupported app: ${APP:-<missing>}" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run with sudo -E"
[[ -n "${ROOT}" ]] || fail "run from the repository checkout"
for command in docker grep head python3 stat; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

# shellcheck source=../lib/secrets.sh
source "${ROOT}/scripts/lib/secrets.sh"

SECRETS_FILE="/mnt/cpool/secrets/runtime/${APP}/.env.secrets"
secrets_assert_file "${SECRETS_FILE}" "${SECRET_KEY}"

if [[ "${APP}" == "defectdojo" ]]; then
  database_url="$(secrets_get_value "${SECRETS_FILE}" DD_DATABASE_URL)" ||
    fail "cannot read DD_DATABASE_URL"
  DB_PASSWORD="$(
    DATABASE_URL="${database_url}" EXPECTED_USER="${DB_USER}" EXPECTED_DB="${DB_NAME}" python3 <<'PY'
import os
from urllib.parse import unquote, urlsplit

parsed = urlsplit(os.environ["DATABASE_URL"])
if parsed.scheme not in {"postgres", "postgresql"}:
    raise SystemExit("DD_DATABASE_URL must use postgres/postgresql")
if unquote(parsed.username or "") != os.environ["EXPECTED_USER"]:
    raise SystemExit("DD_DATABASE_URL user mismatch")
if parsed.path.lstrip("/") != os.environ["EXPECTED_DB"]:
    raise SystemExit("DD_DATABASE_URL database mismatch")
password = unquote(parsed.password or "")
if not password:
    raise SystemExit("DD_DATABASE_URL must contain a password")
print(password, end="")
PY
  )" || fail "invalid DefectDojo database URL"
else
  DB_PASSWORD="$(secrets_get_value "${SECRETS_FILE}" "${SECRET_KEY}")" ||
    fail "cannot read ${SECRET_KEY}"
fi
[[ -n "${DB_PASSWORD}" ]] || fail "database password is empty"

POSTGRES_CONTAINER="$(
  docker ps     --filter 'label=com.docker.compose.project=ix-postgres'     --filter 'label=com.docker.compose.service=postgres'     --format '{{.Names}}' | head -1
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
[[ -n "${POSTGRES_ADMIN}" ]] || fail "cannot determine PostgreSQL admin role"

if [[ "${MODE}" == "--apply" ]]; then
  docker exec -i     -e NABLA_DB_PASSWORD="${DB_PASSWORD}"     -e NABLA_DB_USER="${DB_USER}"     -e NABLA_DB_NAME="${DB_NAME}"     "${POSTGRES_CONTAINER}"     psql --set=ON_ERROR_STOP=1 -U "${POSTGRES_ADMIN}" -d postgres <<'SQL'
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
fi

state="$(
  docker exec "${POSTGRES_CONTAINER}"     psql -U "${POSTGRES_ADMIN}" -d postgres -Atc "
      SELECT
        (SELECT count(*) FROM pg_roles WHERE rolname='${DB_USER}')::text
        || '|' ||
        (SELECT count(*) FROM pg_database WHERE datname='${DB_NAME}')::text
        || '|' ||
        COALESCE((SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='${DB_NAME}'), '');
    "
)"
[[ "${state}" == "1|1|${DB_USER}" ]] ||
  fail "${APP}: role/database not ready (state=${state})"

docker exec   -e PGPASSWORD="${DB_PASSWORD}"   "${POSTGRES_CONTAINER}"   psql --set=ON_ERROR_STOP=1 -h 127.0.0.1 -U "${DB_USER}" -d "${DB_NAME}" -Atc 'SELECT 1' |
  grep -qx '1' ||
  fail "${APP}: dedicated role cannot authenticate"

printf 'OK: shared PostgreSQL ready app=%s role=%s database=%s\n'   "${APP}" "${DB_USER}" "${DB_NAME}"
