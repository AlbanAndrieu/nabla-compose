#!/usr/bin/env bash
set -euo pipefail

SENTRY_URL="${SENTRY_URL:-http://172.17.0.24:9005}"
SENTRY_URL="${SENTRY_URL%/}"
PROJECT_ID="${SENTRY_PROJECT_ID:-1}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-ix-postgres-postgres-1}"
CLICKHOUSE_CONTAINER="${SENTRY_CLICKHOUSE_CONTAINER:-ix-sentry-clickhouse-sentry-clickhouse-1}"

function fail {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

for command in curl docker python3; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

docker inspect "${POSTGRES_CONTAINER}" >/dev/null 2>&1 ||
  fail "PostgreSQL container not found: ${POSTGRES_CONTAINER}"
docker inspect "${CLICKHOUSE_CONTAINER}" >/dev/null 2>&1 ||
  fail "Sentry ClickHouse container not found: ${CLICKHOUSE_CONTAINER}"

if ! curl --fail --silent --show-error --max-time 8 "${SENTRY_URL}/_health/" >/dev/null; then
  fail "Sentry edge health failed at ${SENTRY_URL}/_health/"
fi
printf '✅ Sentry edge health\n'

PUBLIC_KEY="$(
  docker exec "${POSTGRES_CONTAINER}" bash -lc '
    PGUSER="${POSTGRES_USER:-postgres}"
    psql -X -U "${PGUSER}" -d sentry -Atc "
      SELECT public_key
      FROM sentry_projectkey
      WHERE project_id = '"${PROJECT_ID}"'
      ORDER BY id
      LIMIT 1;
    "
  '
)"

[[ -n "${PUBLIC_KEY}" ]] || fail "no project key found for Sentry project ${PROJECT_ID}"

EVENT_UUID="$(python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
)"
EVENT_ID="${EVENT_UUID//-/}"
DSN="${SENTRY_URL/\/\//\/\/${PUBLIC_KEY}@}/${PROJECT_ID}"
TIMESTAMP="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
MESSAGE="Nabla homelab Sentry smoke ${EVENT_ID}"

ENVELOPE="$(
  cat <<EOF
{"event_id":"${EVENT_ID}","dsn":"${DSN}","sent_at":"${TIMESTAMP}"}
{"type":"event","content_type":"application/json"}
{"event_id":"${EVENT_ID}","timestamp":"${TIMESTAMP}","platform":"other","level":"error","logger":"nabla.homelab.smoke","message":{"formatted":"${MESSAGE}"},"tags":{"nabla_smoke":"true","source":"truenas-runtime-audit"}}
EOF
)"

HTTP_CODE="$(
  curl --silent --show-error --max-time 10 \
    --output /tmp/nabla-sentry-smoke-response.txt \
    --write-out '%{http_code}' \
    --request POST \
    --header 'Content-Type: application/x-sentry-envelope' \
    --header "X-Sentry-Auth: Sentry sentry_version=7, sentry_key=${PUBLIC_KEY}" \
    --data-binary "${ENVELOPE}" \
    "${SENTRY_URL}/api/${PROJECT_ID}/envelope/"
)"

case "${HTTP_CODE}" in
  2??)
    printf '✅ Sentry envelope accepted: event_id=%s http=%s\n' "${EVENT_ID}" "${HTTP_CODE}"
    ;;
  *)
    printf 'Sentry response:\n' >&2
    cat /tmp/nabla-sentry-smoke-response.txt >&2 || true
    fail "Sentry envelope rejected with HTTP ${HTTP_CODE}"
    ;;
esac

FOUND=0
for _ in {1..15}; do
  FOUND="$(
    docker exec \
      -e SMOKE_EVENT_UUID="${EVENT_UUID}" \
      -e SMOKE_PROJECT_ID="${PROJECT_ID}" \
      "${CLICKHOUSE_CONTAINER}" \
      bash -lc '
        clickhouse-client \
          --user "$CLICKHOUSE_USER" \
          --password "$CLICKHOUSE_PASSWORD" \
          --database sentry \
          --param_event_uuid "$SMOKE_EVENT_UUID" \
          --param_project_id "$SMOKE_PROJECT_ID" \
          --query "
            SELECT count()
            FROM errors_local
            WHERE project_id = {project_id:UInt64}
              AND event_id = {event_uuid:UUID}
          "
      ' 2>/dev/null || printf '0'
  )"

  if [[ "${FOUND}" =~ ^[0-9]+$ ]] && ((FOUND > 0)); then
    break
  fi
  sleep 2
done

if [[ ! "${FOUND}" =~ ^[0-9]+$ ]] || ((FOUND < 1)); then
  fail "event ${EVENT_ID} was accepted at the edge but not found in sentry.errors_local"
fi

printf '✅ Sentry event queryable in ClickHouse: project=%s event_id=%s rows=%s\n' \
  "${PROJECT_ID}" "${EVENT_ID}" "${FOUND}"
printf '✅ Sentry end-to-end smoke passed: edge -> Relay -> Kafka -> ingest -> Snuba -> ClickHouse\n'
