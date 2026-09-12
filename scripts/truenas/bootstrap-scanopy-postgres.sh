#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
SECRETS_FILE="${SCANOPY_SECRETS_FILE:-/mnt/cpool/secrets/runtime/scanopy/.env.secrets}"
EXPECTED_HOST="${SCANOPY_POSTGRES_HOST:-172.17.0.24}"
EXPECTED_PORT="${SCANOPY_POSTGRES_PORT:-5432}"
EXPECTED_DB="${SCANOPY_POSTGRES_DB:-scanopy}"
EXPECTED_USER="${SCANOPY_POSTGRES_USER:-scanopy}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: $0 [--check|--apply]" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run with sudo so the shared PostgreSQL container can be inspected"
for command in docker python3 stat; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ -f "${SECRETS_FILE}" ]] || fail "missing Scanopy secret file: ${SECRETS_FILE}"
metadata="$(stat -c '%U:%G %a' "${SECRETS_FILE}")"
[[ "${metadata}" == "root:root 600" ]] ||
  fail "${SECRETS_FILE} owner/mode=${metadata}; expected root:root 600"
[[ -s "${SECRETS_FILE}" ]] || fail "${SECRETS_FILE} is empty"

scanopy_password=""
database_url=""
while IFS= read -r -d '' key && IFS= read -r -d '' value; do
  case "${key}" in
    POSTGRES_PASSWORD) scanopy_password="${value}" ;;
    SCANOPY_DATABASE_URL) database_url="${value}" ;;
  esac
done < <(
  python3 - "${SECRETS_FILE}" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

path = Path(sys.argv[1])
wanted = {"POSTGRES_PASSWORD", "SCANOPY_DATABASE_URL"}
values: dict[str, str] = {}


def decode_dotenv(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        body = raw[1:-1]
        out: list[str] = []
        index = 0
        while index < len(body):
            if body[index] == "\\" and index + 1 < len(body):
                out.append(body[index + 1])
                index += 2
                continue
            out.append(body[index])
            index += 1
        return "".join(out)
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return raw[1:-1]
    return raw


for raw_line in path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, raw_value = line.split("=", 1)
    if key in wanted:
        values[key] = decode_dotenv(raw_value)

for key in sorted(wanted):
    value = values.get(key, "")
    sys.stdout.buffer.write(key.encode() + b"\0" + value.encode() + b"\0")
PY
)

[[ -n "${scanopy_password}" ]] || fail "${SECRETS_FILE} must define non-empty POSTGRES_PASSWORD"
[[ -n "${database_url}" ]] || fail "${SECRETS_FILE} must define non-empty SCANOPY_DATABASE_URL"

url_user=""
url_password=""
url_host=""
url_port=""
url_db=""
while IFS= read -r -d '' key && IFS= read -r -d '' value; do
  case "${key}" in
    user) url_user="${value}" ;;
    password) url_password="${value}" ;;
    host) url_host="${value}" ;;
    port) url_port="${value}" ;;
    database) url_db="${value}" ;;
  esac
done < <(
  DATABASE_URL="${database_url}" python3 <<'PY'
from __future__ import annotations

import os
import sys
from urllib.parse import unquote, urlsplit

url = os.environ["DATABASE_URL"]
parsed = urlsplit(url)
if parsed.scheme not in {"postgres", "postgresql"}:
    raise SystemExit("SCANOPY_DATABASE_URL must use postgres/postgresql")
if parsed.username is None or parsed.password is None or parsed.hostname is None:
    raise SystemExit("SCANOPY_DATABASE_URL must include user, password and host")

database = parsed.path.lstrip("/")
if not database:
    raise SystemExit("SCANOPY_DATABASE_URL must include a database name")

pairs = (
    ("user", unquote(parsed.username)),
    ("password", unquote(parsed.password)),
    ("host", parsed.hostname),
    ("port", str(parsed.port or 5432)),
    ("database", database),
)
for key, value in pairs:
    sys.stdout.buffer.write(key.encode() + b"\0" + value.encode() + b"\0")
PY
)

[[ "${url_user}" == "${EXPECTED_USER}" ]] ||
  fail "SCANOPY_DATABASE_URL user=${url_user:-<missing>}; expected ${EXPECTED_USER}"
[[ "${url_password}" == "${scanopy_password}" ]] ||
  fail "SCANOPY_DATABASE_URL password differs from POSTGRES_PASSWORD"
[[ "${url_host}" == "${EXPECTED_HOST}" ]] ||
  fail "SCANOPY_DATABASE_URL host=${url_host:-<missing>}; expected ${EXPECTED_HOST}"
[[ "${url_port}" == "${EXPECTED_PORT}" ]] ||
  fail "SCANOPY_DATABASE_URL port=${url_port:-<missing>}; expected ${EXPECTED_PORT}"
[[ "${url_db}" == "${EXPECTED_DB}" ]] ||
  fail "SCANOPY_DATABASE_URL database=${url_db:-<missing>}; expected ${EXPECTED_DB}"

POSTGRES_CONTAINER="$(
  docker ps \
    --filter 'label=com.docker.compose.project=ix-postgres' \
    --filter 'label=com.docker.compose.service=postgres' \
    --format '{{.Names}}' |
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
  docker exec "${POSTGRES_CONTAINER}" \
    sh -lc 'printf "%s" "${POSTGRES_USER:-postgres}"'
)"
[[ -n "${POSTGRES_ADMIN}" ]] || fail "shared PostgreSQL administrative role could not be determined"

if [[ "${MODE}" == "--apply" ]]; then
  docker exec -i \
    -e SCANOPY_DB_PASSWORD="${scanopy_password}" \
    "${POSTGRES_CONTAINER}" \
    psql \
      --set=ON_ERROR_STOP=1 \
      -U "${POSTGRES_ADMIN}" \
      -d postgres <<'SQL'
\getenv scanopy_password SCANOPY_DB_PASSWORD

SELECT format(
  'CREATE ROLE scanopy LOGIN PASSWORD %L',
  :'scanopy_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = 'scanopy'
) \gexec

SELECT format(
  'ALTER ROLE scanopy PASSWORD %L',
  :'scanopy_password'
) \gexec

SELECT 'CREATE DATABASE scanopy OWNER scanopy'
WHERE NOT EXISTS (
  SELECT 1 FROM pg_database WHERE datname = 'scanopy'
) \gexec

ALTER DATABASE scanopy OWNER TO scanopy;
SQL
fi

state="$(
  docker exec "${POSTGRES_CONTAINER}" \
    psql -U "${POSTGRES_ADMIN}" -d postgres -Atc "
      SELECT
        (SELECT count(*) FROM pg_roles WHERE rolname='scanopy')::text
        || '|' ||
        (SELECT count(*) FROM pg_database WHERE datname='scanopy')::text
        || '|' ||
        COALESCE((
          SELECT pg_get_userbyid(datdba)
          FROM pg_database
          WHERE datname='scanopy'
        ), '');
    "
)"
[[ "${state}" == "1|1|scanopy" ]] ||
  fail "shared PostgreSQL Scanopy role/database not ready (state=${state})"

if ! docker exec \
  -e PGPASSWORD="${scanopy_password}" \
  "${POSTGRES_CONTAINER}" \
  psql \
    --set=ON_ERROR_STOP=1 \
    -h 127.0.0.1 \
    -U "${EXPECTED_USER}" \
    -d "${EXPECTED_DB}" \
    -Atc 'SELECT 1' |
  grep -qx '1'; then
  fail "Scanopy role cannot authenticate to the shared PostgreSQL database"
fi

printf '✅ shared PostgreSQL ready for Scanopy: host=%s port=%s role=%s database=%s\n' \
  "${EXPECTED_HOST}" "${EXPECTED_PORT}" "${EXPECTED_USER}" "${EXPECTED_DB}"
