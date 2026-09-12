#!/usr/bin/env bash
set -euo pipefail

FASTAPI_URL="${FASTAPI_URL:-http://127.0.0.1:8091}"
FASTAPI_URL="${FASTAPI_URL%/}"
PYROSCOPE_URL="${PYROSCOPE_URL:-http://127.0.0.1:4040}"
PYROSCOPE_URL="${PYROSCOPE_URL%/}"
PROJECT_ID="${SENTRY_PROJECT_ID:-2}"
CLICKHOUSE_CONTAINER="${SENTRY_CLICKHOUSE_CONTAINER:-ix-sentry-clickhouse-sentry-clickhouse-1}"
APP_NAME="${FASTAPI_OBSERVABILITY_APP_NAME:-fastapi-sample}"
ATTEMPTS="${FASTAPI_OBSERVABILITY_ATTEMPTS:-30}"
DELAY_SECONDS="${FASTAPI_OBSERVABILITY_DELAY_SECONDS:-2}"
PYROSCOPE_LOOKBACK_SECONDS="${PYROSCOPE_LOOKBACK_SECONDS:-3600}"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

for command in curl docker jq python3; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

docker inspect "${CLICKHOUSE_CONTAINER}" >/dev/null 2>&1 ||
  fail "Sentry ClickHouse container not found: ${CLICKHOUSE_CONTAINER}"

TRACE_ID="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
PARENT_SPAN_ID="$(python3 -c 'import secrets; print(secrets.token_hex(8))')"
TRACE_UUID="$(python3 - "${TRACE_ID}" <<'PY'
import sys
import uuid
print(uuid.UUID(sys.argv[1]))
PY
)"

response="$(
  curl --silent --show-error --max-time 10 \
    --header "sentry-trace: ${TRACE_ID}-${PARENT_SPAN_ID}-1" \
    "${FASTAPI_URL}/sentry-debug"
)"
EVENT_ID="$(jq -r '.event_id // empty' <<<"${response}")"
[[ "${EVENT_ID}" =~ ^[0-9a-fA-F]{32}$ ]] || {
  printf '%s\n' "${response}" >&2
  fail "FastAPI /sentry-debug did not return a Sentry event_id"
}
EVENT_UUID="$(python3 - "${EVENT_ID}" <<'PY'
import sys
import uuid
print(uuid.UUID(sys.argv[1]))
PY
)"
printf '✅ FastAPI emitted Sentry test event: project=%s event_id=%s trace_id=%s\n' \
  "${PROJECT_ID}" "${EVENT_ID}" "${TRACE_ID}"

ERROR_ROW=""
for ((attempt = 1; attempt <= ATTEMPTS; attempt++)); do
  ERROR_ROW="$(
    docker exec \
      -e CHECK_EVENT_UUID="${EVENT_UUID}" \
      -e CHECK_PROJECT_ID="${PROJECT_ID}" \
      "${CLICKHOUSE_CONTAINER}" \
      bash -lc '
        clickhouse-client \
          --user "$CLICKHOUSE_USER" \
          --password "$CLICKHOUSE_PASSWORD" \
          --database sentry \
          --param_event_uuid="$CHECK_EVENT_UUID" \
          --param_project_id="$CHECK_PROJECT_ID" \
          --query "
            SELECT concat(toString(group_id), char(9), toString(trace_id), char(9), transaction_name)
            FROM errors_local
            WHERE project_id = {project_id:UInt64}
              AND event_id = {event_uuid:UUID}
            LIMIT 1
          "
      ' 2>/dev/null || true
  )"
  [[ -n "${ERROR_ROW}" ]] && break
  sleep "${DELAY_SECONDS}"
done

[[ -n "${ERROR_ROW}" ]] ||
  fail "Sentry event ${EVENT_ID} was not persisted in errors_local"

IFS=$'\t' read -r GROUP_ID STORED_TRACE_ID TRANSACTION_NAME <<<"${ERROR_ROW}"
[[ "${STORED_TRACE_ID}" == "${TRACE_UUID}" ]] ||
  fail "Sentry error trace mismatch: expected=${TRACE_UUID} stored=${STORED_TRACE_ID}"
printf '✅ Sentry error persisted and correlated: issue=%s transaction=%s\n' \
  "${GROUP_ID}" "${TRANSACTION_NAME}"

EAP_SPANS="$(
  docker exec \
    -e CHECK_TRACE_UUID="${TRACE_UUID}" \
    -e CHECK_PROJECT_ID="${PROJECT_ID}" \
    "${CLICKHOUSE_CONTAINER}" \
    bash -lc '
      clickhouse-client \
        --user "$CLICKHOUSE_USER" \
        --password "$CLICKHOUSE_PASSWORD" \
        --database sentry \
        --param_trace_uuid="$CHECK_TRACE_UUID" \
        --param_project_id="$CHECK_PROJECT_ID" \
        --query "
          SELECT count()
          FROM eap_spans_local
          WHERE project_id = {project_id:UInt64}
            AND trace_id = {trace_uuid:UUID}
        "
    ' 2>/dev/null || printf '0'
)"
TRANSACTIONS="$(
  docker exec \
    -e CHECK_TRACE_UUID="${TRACE_UUID}" \
    -e CHECK_PROJECT_ID="${PROJECT_ID}" \
    "${CLICKHOUSE_CONTAINER}" \
    bash -lc '
      clickhouse-client \
        --user "$CLICKHOUSE_USER" \
        --password "$CLICKHOUSE_PASSWORD" \
        --database sentry \
        --param_trace_uuid="$CHECK_TRACE_UUID" \
        --param_project_id="$CHECK_PROJECT_ID" \
        --query "
          SELECT count()
          FROM transactions_local
          WHERE project_id = {project_id:UInt64}
            AND trace_id = {trace_uuid:UUID}
        "
    ' 2>/dev/null || printf '0'
)"

[[ "${EAP_SPANS}" =~ ^[0-9]+$ ]] || EAP_SPANS=0
[[ "${TRANSACTIONS}" =~ ^[0-9]+$ ]] || TRANSACTIONS=0
if ((EAP_SPANS + TRANSACTIONS < 1)); then
  fail "Sentry error is correlated to trace ${TRACE_ID}, but no transaction/span was persisted (eap_spans=${EAP_SPANS}, transactions=${TRANSACTIONS})"
fi
printf '✅ Sentry tracing persisted: eap_spans=%s transactions=%s\n' \
  "${EAP_SPANS}" "${TRANSACTIONS}"

if ! curl --fail --silent --show-error --max-time 5 "${PYROSCOPE_URL}/ready" >/dev/null; then
  fail "Pyroscope readiness failed at ${PYROSCOPE_URL}/ready"
fi
printf '✅ Pyroscope readiness\n'

END_MS="$(( $(date +%s) * 1000 ))"
START_MS="$(( END_MS - PYROSCOPE_LOOKBACK_SECONDS * 1000 ))"
PYROSCOPE_SERIES="$(
  curl --fail --silent --show-error --max-time 10 \
    --header 'Content-Type: application/json' \
    --data "{\"start\":${START_MS},\"end\":${END_MS},\"matchers\":[\"{service_name=\\\"${APP_NAME}\\\"}\"]}" \
    "${PYROSCOPE_URL}/querier.v1.QuerierService/Series"
)" || fail "Pyroscope series query failed for service_name=${APP_NAME}"

if ! grep -Fq "${APP_NAME}" <<<"${PYROSCOPE_SERIES}"; then
  printf '%s\n' "${PYROSCOPE_SERIES}" >&2
  fail "Pyroscope has no recent profile series for service_name=${APP_NAME} in the last ${PYROSCOPE_LOOKBACK_SECONDS}s"
fi
printf '✅ Pyroscope recent profile series found: service_name=%s lookback=%ss\n' \
  "${APP_NAME}" "${PYROSCOPE_LOOKBACK_SECONDS}"

printf '✅ FastAPI observability smoke passed: Sentry error + trace + Pyroscope profile\n'
