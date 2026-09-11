#!/usr/bin/env bash
set -euo pipefail

# Keep interactive diagnostics compact while preserving full CI/non-TTY output.
if [[ "${NABLA_DIAGNOSTIC_WRAPPED:-0}" != "1" &&
      "${DIAGNOSTIC_FULL_OUTPUT:-0}" != "1" &&
      ( -t 1 || "${DIAGNOSTIC_COMPACT_OUTPUT:-0}" == "1" ) ]]; then
  NABLA_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  NABLA_DIAGNOSTIC_WRAPPER="$(dirname -- "${NABLA_SCRIPT_DIR}")/run-diagnostic.sh"
  exec "${NABLA_DIAGNOSTIC_WRAPPER}" \
    "${NABLA_SCRIPT_DIR}/$(basename -- "${BASH_SOURCE[0]}")" "$@"
fi

SENTRY_URL="${SENTRY_URL:-http://172.17.0.24:9005}"
SENTRY_URL="${SENTRY_URL%/}"
PROJECT_ID="${SENTRY_PROJECT_ID:-1}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-ix-postgres-postgres-1}"
CLICKHOUSE_CONTAINER="${SENTRY_CLICKHOUSE_CONTAINER:-ix-sentry-clickhouse-sentry-clickhouse-1}"
KAFKA_CONTAINER="${SENTRY_KAFKA_CONTAINER:-ix-kafka-kafka-1}"
RELAY_CONTAINER="${SENTRY_RELAY_CONTAINER:-ix-sentry-relay-1}"
SMOKE_ATTEMPTS="${SENTRY_SMOKE_ATTEMPTS:-60}"
SMOKE_DELAY_SECONDS="${SENTRY_SMOKE_DELAY_SECONDS:-2}"

function fail {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

function kafka_group_topic_log_end {
  local group="$1"
  local topic="$2"

  docker exec "${KAFKA_CONTAINER}" kafka-consumer-groups \
    --bootstrap-server kafka:9092 \
    --describe \
    --group "${group}" 2>/dev/null |
    awk -v topic="${topic}" '
      $2 == topic && $5 ~ /^[0-9]+$/ { sum += $5; found = 1 }
      END { if (found) print sum; else print "-1" }
    '
}

function print_ingestion_diagnostics {
  local container state health
  local ingest_after events_after
  local containers=(
    "${RELAY_CONTAINER}"
    ix-sentry-sentry-events-consumer-1
    ix-sentry-snuba-errors-consumer-1
    ix-sentry-sentry-post-process-forwarder-errors-1
  )

  printf '\n==> Sentry ingestion-chain diagnostics\n' >&2
  for container in "${containers[@]}"; do
    if ! docker inspect "${container}" >/dev/null 2>&1; then
      printf '%s MISSING\n' "${container}" >&2
      continue
    fi
    state="$(docker inspect "${container}" --format '{{.State.Status}}')"
    health="$(docker inspect "${container}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
    printf '%s state=%s health=%s restarts=%s\n' \
      "${container}" "${state}" "${health}" \
      "$(docker inspect "${container}" --format '{{.RestartCount}}')" >&2
    docker logs --since 10m "${container}" 2>&1 |
      grep -Ei "${EVENT_ID:-no-event-id}|error|exception|kafka|coordinator|timeout|partition|health|clickhouse|drop|reject|project" |
      tail -30 >&2 || true
  done

  if docker inspect "${KAFKA_CONTAINER}" >/dev/null 2>&1; then
    printf '\nKafka broker state:\n' >&2
    docker inspect "${KAFKA_CONTAINER}" --format \
      'state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} restarts={{.RestartCount}}' >&2 || true
    docker exec "${KAFKA_CONTAINER}" kafka-topics \
      --bootstrap-server kafka:9092 \
      --list >/dev/null 2>&1 &&
      printf 'broker metadata request=OK\n' >&2 ||
      printf 'broker metadata request=FAILED\n' >&2

    for group in ingest-consumer snuba-consumers post-process-forwarder; do
      printf '\nKafka group %s:\n' "${group}" >&2
      docker exec "${KAFKA_CONTAINER}" kafka-consumer-groups \
        --bootstrap-server kafka:9092 \
        --describe \
        --group "${group}" 2>&1 >&2 || true
    done

    ingest_after="$(kafka_group_topic_log_end ingest-consumer ingest-events || printf '%s' -1)"
    events_after="$(kafka_group_topic_log_end snuba-consumers events || printf '%s' -1)"
    printf '\nKafka topic progress during smoke:\n' >&2
    printf '  ingest-events log-end before=%s after=%s\n' \
      "${INGEST_BEFORE:-unknown}" "${ingest_after}" >&2
    printf '  events        log-end before=%s after=%s\n' \
      "${EVENTS_BEFORE:-unknown}" "${events_after}" >&2

    if [[ "${INGEST_BEFORE:-}" =~ ^[0-9]+$ && "${ingest_after}" =~ ^[0-9]+$ &&
          "${EVENTS_BEFORE:-}" =~ ^[0-9]+$ && "${events_after}" =~ ^[0-9]+$ ]]; then
      if ((ingest_after <= INGEST_BEFORE)); then
        printf '  stage=relay-kafka-publish: edge accepted the envelope but ingest-events did not advance\n' >&2
      elif ((events_after <= EVENTS_BEFORE)); then
        printf '  stage=ingest-consumer: ingest-events advanced but events did not\n' >&2
      else
        printf '  stage=snuba-clickhouse: events advanced but errors_local still lacks the event\n' >&2
      fi
    fi

    printf '\nRecent Kafka broker warnings/errors:\n' >&2
    docker logs --since 10m "${KAFKA_CONTAINER}" 2>&1 |
      grep -Ei 'error|warn|coordinator|timeout|controller|raft|request|disconnect' |
      tail -40 >&2 || true
  fi
}

for command in curl docker python3; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

docker inspect "${POSTGRES_CONTAINER}" >/dev/null 2>&1 ||
  fail "PostgreSQL container not found: ${POSTGRES_CONTAINER}"
docker inspect "${CLICKHOUSE_CONTAINER}" >/dev/null 2>&1 ||
  fail "Sentry ClickHouse container not found: ${CLICKHOUSE_CONTAINER}"
docker inspect "${KAFKA_CONTAINER}" >/dev/null 2>&1 ||
  fail "Kafka container not found: ${KAFKA_CONTAINER}"
docker inspect "${RELAY_CONTAINER}" >/dev/null 2>&1 ||
  fail "Sentry Relay container not found: ${RELAY_CONTAINER}"

if ! docker exec "${KAFKA_CONTAINER}" kafka-topics \
  --bootstrap-server kafka:9092 \
  --list >/dev/null 2>&1; then
  fail "Kafka broker metadata request failed before Sentry smoke"
fi
printf '✅ Kafka broker metadata readiness\n'

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

INGEST_BEFORE="$(kafka_group_topic_log_end ingest-consumer ingest-events || printf '%s' -1)"
EVENTS_BEFORE="$(kafka_group_topic_log_end snuba-consumers events || printf '%s' -1)"

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
for ((attempt = 1; attempt <= SMOKE_ATTEMPTS; attempt++)); do
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
          --param_event_uuid="$SMOKE_EVENT_UUID" \
          --param_project_id="$SMOKE_PROJECT_ID" \
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
  sleep "${SMOKE_DELAY_SECONDS}"
done

if [[ ! "${FOUND}" =~ ^[0-9]+$ ]] || ((FOUND < 1)); then
  print_ingestion_diagnostics
  fail "event ${EVENT_ID} was accepted at the edge but not found in sentry.errors_local after $((SMOKE_ATTEMPTS * SMOKE_DELAY_SECONDS))s"
fi

printf '✅ Sentry event queryable in ClickHouse: project=%s event_id=%s rows=%s\n' \
  "${PROJECT_ID}" "${EVENT_ID}" "${FOUND}"
printf '✅ Sentry end-to-end smoke passed: edge -> Relay -> Kafka -> ingest -> Snuba -> ClickHouse\n'
