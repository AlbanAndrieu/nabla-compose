#!/usr/bin/env bash
# Logical backup of the shared PostgreSQL databases: one pg_dump -Fc archive per
# database, verified with pg_restore --list, sha256 sidecar, pruned by age.
# Runs inside the postgres image (client == server version). Secrets come from
# the environment (env_file); the password is never printed or passed on argv.
set -euo pipefail

: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${BACKUP_DATABASES:?BACKUP_DATABASES is required}"

export PGPASSWORD="${POSTGRES_PASSWORD}"
unset POSTGRES_PASSWORD
PGPORT="${POSTGRES_PORT:-5432}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
[[ "${KEEP_DAYS}" =~ ^[0-9]+$ ]] || { echo "BACKUP_KEEP_DAYS must be an integer" >&2; exit 2; }
[[ -d "${BACKUP_DIR}" && -w "${BACKUP_DIR}" ]] || { echo "${BACKUP_DIR} is not a writable directory" >&2; exit 2; }

# BACKUP_REQUIRE_ALL=true turns a missing database into a failure; by default a
# database that is not created yet (staged rollout) is reported as SKIP.
REQUIRE_ALL="${BACKUP_REQUIRE_ALL:-false}"
# BACKUP_SERIES separates schedules with their own retention (for example the
# monthly and yearly Sentry archives): archives land in <database>-<series>/
# and only the directories written by this run are pruned, so the daily
# 14-day retention never deletes a monthly or yearly archive.
SERIES="${BACKUP_SERIES:-}"
[[ "${SERIES}" =~ ^[a-z]{0,16}$ ]] || { echo "BACKUP_SERIES must be lowercase letters" >&2; exit 2; }
marker="${BACKUP_DIR}/.last-success${SERIES:+-${SERIES}}.json"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
failures=0
completed=()
skipped=()

for database in ${BACKUP_DATABASES}; do
  if ! [[ "${database}" =~ ^[a-z][a-z0-9_]{0,62}$ ]]; then
    echo "invalid database name: ${database}" >&2
    exit 2
  fi
  exists="$(psql -h "${POSTGRES_HOST}" -p "${PGPORT}" -U "${POSTGRES_USER}" -d postgres -Atc \
    "SELECT count(*) FROM pg_database WHERE datname = '${database}'" 2>/dev/null || echo "?")"
  if [[ "${exists}" != "1" ]]; then
    if [[ "${REQUIRE_ALL}" == "true" || "${exists}" == "?" ]]; then
      printf 'FAIL %s (database not found or not reachable)\n' "${database}" >&2
      failures=$((failures + 1))
    else
      printf 'SKIP %s (database not created yet)\n' "${database}"
      skipped+=("${database}")
    fi
    continue
  fi
  target_dir="${BACKUP_DIR}/${database}${SERIES:+-${SERIES}}"
  mkdir -p "${target_dir}"
  partial="${target_dir}/.${database}-${stamp}.dump.part"
  archive="${target_dir}/${database}-${stamp}.dump"
  if pg_dump -h "${POSTGRES_HOST}" -p "${PGPORT}" -U "${POSTGRES_USER}" -d "${database}" \
    --format=custom --compress=6 --no-owner --no-privileges --file="${partial}" &&
    pg_restore --list "${partial}" >/dev/null; then
    mv -f "${partial}" "${archive}"
    (cd "${target_dir}" && sha256sum "$(basename "${archive}")" >"$(basename "${archive}").sha256")
    printf 'OK %s %s bytes\n' "${database}" "$(stat -c %s "${archive}")"
    completed+=("${database}")
  else
    rm -f "${partial}"
    printf 'FAIL %s\n' "${database}" >&2
    failures=$((failures + 1))
  fi
done

# A successful run must produce at least one validated archive. During a
# staged rollout every database can be absent: that is NOT backup success and
# must not refresh the last-success marker or prune older recovery points.
if (("${#completed[@]}" == 0)); then
  printf 'FAIL no database backup completed (skipped=%s failed=%s)\n' \
    "${#skipped[@]}" "${failures}" >&2
  exit 1
fi

if ((failures == 0)); then
  # Prune only after the entire backup wave completed successfully. A failed
  # database must keep its older recovery points intact.
  for database in "${completed[@]}"; do
    target_dir="${BACKUP_DIR}/${database}${SERIES:+-${SERIES}}"
    find "${target_dir}" -type f \( -name '*.dump' -o -name '*.dump.sha256' \) \
      -mtime +"${KEEP_DAYS}" -delete
    find "${target_dir}" -type f -name '.*.dump.part' -mmin +720 -delete
  done
  printf '{"completed_at":"%s","series":"%s","databases":"%s","skipped":"%s","keep_days":%s}\n' \
    "${stamp}" "${SERIES:-daily}" "${completed[*]}" "${skipped[*]}" "${KEEP_DAYS}" >"${marker}"
  echo "backup completed: ${completed[*]}${skipped[*]:+ (skipped: ${skipped[*]})}"
  exit 0
fi
echo "backup failed for ${failures} database(s)" >&2
exit 1
