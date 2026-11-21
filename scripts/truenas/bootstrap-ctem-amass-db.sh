#!/usr/bin/env bash
# Bootstrap Amass assetdb on the existing TrueNAS PostgreSQL App, not a new container.
# No password is placed on argv or in stdout. Requires explicitly approved apply.
set -euo pipefail
set +x
MODE="${1:---check}"
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib/common.sh
source "${ROOT}/scripts/lib/common.sh"
# shellcheck source=../lib/postgres.sh
source "${ROOT}/scripts/lib/postgres.sh"
# shellcheck source=../lib/secrets.sh
source "${ROOT}/scripts/lib/secrets.sh"
SECRET=/mnt/cpool/secrets/runtime/ctem-amass/.env.secrets
ROLE=amass
DATABASE=assetdb
case "${MODE}" in --check|--apply) ;; *) fail "usage: $0 [--check|--apply]" ;; esac
require_root "TrueNAS shared PostgreSQL bootstrap requires root"
require_commands docker stat python3
container="$(postgres_shared_container)" || exit 1
admin="$(postgres_admin_role "${container}")" || exit 1
state="$(postgres_role_database_state "${container}" "${admin}" "${ROLE}" "${DATABASE}")"
printf 'CHECK: shared PostgreSQL role/database state=%s (role|database|owner)\n' "${state}"
if [[ "${MODE}" == --check ]]; then
  postgres_database_exists "${container}" "${admin}" "${DATABASE}" &&
    docker exec "${container}" psql -U "${admin}" -d "${DATABASE}" -Atc \
      "SELECT count(*) FROM pg_extension WHERE extname='pg_trgm';" |
      grep -qx 1 && echo "CHECK: shared assetdb pg_trgm ready" || echo "CHECK: shared assetdb pg_trgm NOT_VERIFIED"
  exit 0
fi
[[ "${CTEM_AMASS_DB_APPROVED:-}" == YES ]] ||
  fail "CTEM_AMASS_DB_APPROVED=YES required to create dedicated assetdb on shared PostgreSQL"
secrets_assert_file "${SECRET}" AMASS_DB_PASSWORD AMASS_DB_USER AMASS_DB_NAME AMASS_DB_HOST ||
  fail "private CTEM PostgreSQL secret contract not met"
for pair in "AMASS_DB_USER:amass" "AMASS_DB_NAME:assetdb"; do
  key="${pair%%:*}"
  expected="${pair#*:}"
  [[ "$(secrets_get_value "${SECRET}" "${key}")" == "${expected}" ]] ||
    fail "unexpected ${key}; refuse to touch any other role/database"
done
password="$(secrets_get_value "${SECRET}" AMASS_DB_PASSWORD)"
[[ -n "${password}" && "${password}" != *[$'\r\n']* ]] || fail "invalid Amass password"
NABLA_DB_PASSWORD="${password}" postgres_ensure_role_database "${container}" "${admin}" "${ROLE}" "${DATABASE}"
unset password
# Do not create an extension in any existing application database.
docker exec -i "${container}" psql -X --set=ON_ERROR_STOP=1 -U "${admin}" -d "${DATABASE}" <<'SQL'
CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA public;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE assetdb TO amass;
GRANT USAGE, CREATE ON SCHEMA public TO amass;
ALTER ROLE amass NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER DATABASE assetdb SET timezone TO 'UTC';
-- CTEM report metadata is deliberately separate from the Amass asset graph.
-- This creates a table within the existing DB, never another PostgreSQL App.
CREATE SCHEMA IF NOT EXISTS ctem AUTHORIZATION amass;
CREATE TABLE IF NOT EXISTS ctem.scan_reports (
  sha256 char(64) PRIMARY KEY,
  scanner text NOT NULL CHECK (scanner IN ('amass', 'checkdmarc')),
  checked_at timestamptz NOT NULL,
  status text NOT NULL,
  catalog_revision text,
  summary jsonb NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now()
);
GRANT USAGE, CREATE ON SCHEMA ctem TO amass;
GRANT SELECT, INSERT ON ctem.scan_reports TO amass;

SQL
state="$(postgres_role_database_state "${container}" "${admin}" "${ROLE}" "${DATABASE}")"
[[ "${state}" == "1|1|amass" ]] || fail "assetdb not owned by dedicated amass role"
ok "existing PostgreSQL App: assetdb and pg_trgm prepared (private CTEM access)"
