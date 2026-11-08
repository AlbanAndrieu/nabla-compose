#!/usr/bin/env bash
# Provision one application's role and database on the shared TrueNAS
# PostgreSQL App, from the application's canonical runtime secret.
#
#   sudo bash scripts/truenas/bootstrap-app-postgres.sh --check <app>
#   sudo bash scripts/truenas/bootstrap-app-postgres.sh --apply <app>
#   bash scripts/truenas/bootstrap-app-postgres.sh --describe <app>
#
# --check (default) only verifies; --apply is idempotent (CREATE/ALTER ROLE,
# CREATE DATABASE, ALTER OWNER). The password is read from the 0600 secret
# file and only ever travels through the environment of `docker exec -e`.
# The per-application wrappers (bootstrap-joplin-postgres.sh, ...) delegate
# here and remain supported entry points.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"
# shellcheck source=../lib/secrets.sh
source "${SCRIPT_DIR}/../lib/secrets.sh"
# shellcheck source=../lib/postgres.sh
source "${SCRIPT_DIR}/../lib/postgres.sh"

MODE="${1:---check}"
APP="${2:-}"
RUNTIME_SECRETS_ROOT="${NABLA_RUNTIME_ENV_ROOT:-/mnt/cpool/secrets/runtime}"
EXPECTED_HOST="${NABLA_POSTGRES_HOST:-172.17.0.24}"
EXPECTED_PORT="${NABLA_POSTGRES_PORT:-5432}"
SUPPORTED_APPS="homeassistant joplin scanopy plumber netbox dependency-track defectdojo keycloak"

usage() {
  printf 'usage: %s [--check|--apply|--describe] <%s>\n' "$0" "${SUPPORTED_APPS// /|}" >&2
  exit 1
}

case "${MODE}" in
--check | --apply | --describe) ;;
*) usage ;;
esac
[[ -n "${APP}" ]] || usage

# Application table: secret file, secret key, role, database, extra contract.
# PASSWORD_SOURCE=value reads the key as the password; url parses the password
# out of a postgres:// URL whose user/database must match the table.
SECRETS_FILE="${RUNTIME_SECRETS_ROOT}/${APP}/.env.secrets"
PASSWORD_SOURCE="value"
URL_KEY=""
case "${APP}" in
homeassistant | joplin | scanopy)
  SECRET_KEY="POSTGRES_PASSWORD"
  DB_USER="${APP}"
  DB_NAME="${APP}"
  ;;
plumber)
  SECRET_KEY="JOBS_DB_PASSWORD"
  DB_USER="jobs"
  DB_NAME="jobs"
  ;;
netbox)
  SECRET_KEY="DB_PASSWORD"
  DB_USER="netbox"
  DB_NAME="netbox"
  ;;
dependency-track)
  SECRET_KEY="ALPINE_DATABASE_PASSWORD"
  DB_USER="dependencytrack"
  DB_NAME="dependencytrack"
  ;;
defectdojo)
  SECRET_KEY="DD_DATABASE_URL"
  PASSWORD_SOURCE="url"
  DB_USER="defectdojo"
  DB_NAME="defectdojo"
  ;;
keycloak)
  # Keycloak keeps its historical secret location (apps/keycloak/compose.yml env_file).
  SECRETS_FILE="${KEYCLOAK_SECRETS_FILE:-/mnt/cpool/keycloak/.env.secrets}"
  SECRET_KEY="KC_DB_PASSWORD"
  DB_USER="keycloak"
  DB_NAME="keycloak"
  ;;
*) fail "unsupported app: ${APP} (supported: ${SUPPORTED_APPS})" ;;
esac
# Scanopy also carries the complete URL; it must agree with POSTGRES_PASSWORD.
[[ "${APP}" != "scanopy" ]] || URL_KEY="SCANOPY_DATABASE_URL"
SECRETS_FILE="${NABLA_APP_SECRETS_FILE:-${SECRETS_FILE}}"

if [[ "${MODE}" == "--describe" ]]; then
  printf '%s\n' "app=${APP}" "role=${DB_USER}" "database=${DB_NAME}" \
    "host=${EXPECTED_HOST}" "port=${EXPECTED_PORT}" \
    "secret_file=${SECRETS_FILE}" "secret_key=${SECRET_KEY}" \
    "password_source=${PASSWORD_SOURCE}" "url_key=${URL_KEY:-none}"
  exit 0
fi

require_root "run with sudo so the shared PostgreSQL container can be inspected"
require_commands docker grep head python3 stat

secrets_assert_file "${SECRETS_FILE}" "${SECRET_KEY}" ${URL_KEY:+"${URL_KEY}"} ||
  fail "${APP}: secret contract is not satisfied"

# Read the password; validate URL-shaped secrets against the table without
# printing any of their components.
assert_url_matches() {
  local url_key="$1" expected_password="$2" value component expected
  value="$(secrets_get_value "${SECRETS_FILE}" "${url_key}")" || fail "cannot read ${url_key}"
  for component in user host port database; do
    case "${component}" in
    user) expected="${DB_USER}" ;;
    host) expected="${EXPECTED_HOST}" ;;
    port) expected="${EXPECTED_PORT}" ;;
    database) expected="${DB_NAME}" ;;
    esac
    [[ "$(NABLA_DB_URL="${value}" postgres_url_component "${component}")" == "${expected}" ]] ||
      fail "${APP}: ${url_key} ${component} does not match the expected ${component} (${expected})"
  done
  if [[ -n "${expected_password}" ]]; then
    [[ "$(NABLA_DB_URL="${value}" postgres_url_component password)" == "${expected_password}" ]] ||
      fail "${APP}: ${url_key} password differs from ${SECRET_KEY}"
  fi
}

if [[ "${PASSWORD_SOURCE}" == "url" ]]; then
  assert_url_matches "${SECRET_KEY}" ""
  url_value="$(secrets_get_value "${SECRETS_FILE}" "${SECRET_KEY}")" || fail "cannot read ${SECRET_KEY}"
  db_password="$(NABLA_DB_URL="${url_value}" postgres_url_component password)"
  unset url_value
else
  db_password="$(secrets_get_value "${SECRETS_FILE}" "${SECRET_KEY}")" ||
    fail "unable to read ${SECRET_KEY} from ${SECRETS_FILE}"
fi
[[ -n "${db_password}" ]] || fail "${SECRETS_FILE} must define non-empty ${SECRET_KEY}"
[[ -z "${URL_KEY}" ]] || assert_url_matches "${URL_KEY}" "${db_password}"

POSTGRES_CONTAINER="$(postgres_shared_container)" || exit 1
POSTGRES_ADMIN="$(postgres_admin_role "${POSTGRES_CONTAINER}")" || exit 1

if [[ "${MODE}" == "--apply" ]]; then
  NABLA_DB_PASSWORD="${db_password}" \
    postgres_ensure_role_database "${POSTGRES_CONTAINER}" "${POSTGRES_ADMIN}" "${DB_USER}" "${DB_NAME}"
fi

state="$(postgres_role_database_state "${POSTGRES_CONTAINER}" "${POSTGRES_ADMIN}" "${DB_USER}" "${DB_NAME}")"
[[ "${state}" == "1|1|${DB_USER}" ]] ||
  fail "${APP}: role/database not ready (state=${state}); run: sudo bash scripts/truenas/bootstrap-app-postgres.sh --apply ${APP}"

PGPASSWORD="${db_password}" postgres_assert_login "${POSTGRES_CONTAINER}" "${DB_USER}" "${DB_NAME}" ||
  fail "${APP}: dedicated role cannot authenticate to the shared PostgreSQL database"
unset db_password

[[ "${MODE}" != "--check" ]] || printf '%s\n' "${APP}_postgres_mutations=0"
ok "shared PostgreSQL ready app=${APP} role=${DB_USER} database=${DB_NAME} host=${EXPECTED_HOST} port=${EXPECTED_PORT}"
