#!/usr/bin/env bash
set -euo pipefail

APP_ID="${SENTRY_APP_ID:-sentry}"
WAIT_ATTEMPTS="${SENTRY_SNUBA_RECOVERY_ATTEMPTS:-60}"
WAIT_DELAY="${SENTRY_SNUBA_RECOVERY_DELAY_SECONDS:-5}"
STABILITY_DELAY="${SENTRY_SNUBA_STABILITY_DELAY_SECONDS:-65}"
KAFKA_CONTAINER="${SENTRY_KAFKA_CONTAINER:-ix-kafka-kafka-1}"

# Exact allow-list for the errors-only ingestion path. Never broaden this to
# arbitrary ix-sentry-* containers: migrations, web and task services have
# different lifecycle semantics.
TARGETS=(
  ix-sentry-snuba-errors-consumer-1
  ix-sentry-snuba-outcomes-consumer-1
  ix-sentry-snuba-outcomes-billing-consumer-1
  ix-sentry-snuba-group-attributes-consumer-1
  ix-sentry-snuba-replacer-1
  ix-sentry-snuba-subscription-consumer-events-1
  ix-sentry-sentry-events-consumer-1
  ix-sentry-sentry-attachments-consumer-1
  ix-sentry-sentry-post-process-forwarder-errors-1
)

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "run with sudo"

for command in docker midclt jq; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

app_state="$(
  midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]" |
    jq -r '.[0].state // "MISSING"'
)"
[[ "${app_state}" != "MISSING" ]] || fail "TrueNAS app ${APP_ID} is missing"

printf 'Sentry aggregate state before targeted recovery: %s\n' "${app_state}"

for container in "${TARGETS[@]}"; do
  docker inspect "${container}" >/dev/null 2>&1 ||
    fail "target Sentry consumer container is missing: ${container}"

  state="$(docker inspect "${container}" --format '{{.State.Status}}')"
  health="$(docker inspect "${container}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
  printf '%s before: state=%s health=%s\n' "${container}" "${state}" "${health}"

  [[ "${state}" == "running" ]] ||
    fail "${container} is not running; use the full Sentry diagnostic before recovery"

  case "${health}" in
    healthy)
      printf '  already healthy; no restart needed\n'
      ;;
    starting)
      printf '  still starting; do not reset its healthcheck grace period\n'
      ;;
    unhealthy)
      printf '  restarting only this unhealthy Sentry consumer...\n'
      docker restart "${container}" >/dev/null
      ;;
    *)
      fail "${container} has no usable Docker health status: ${health}"
      ;;
  esac
done

for ((attempt = 1; attempt <= WAIT_ATTEMPTS; attempt++)); do
  all_healthy=1
  for container in "${TARGETS[@]}"; do
    state="$(docker inspect "${container}" --format '{{.State.Status}}')"
    health="$(docker inspect "${container}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
    if [[ "${state}" != "running" || "${health}" != "healthy" ]]; then
      all_healthy=0
    fi
  done

  if [[ "${all_healthy}" -eq 1 ]]; then
    break
  fi

  if ((attempt == 1 || attempt % 12 == 0)); then
    printf 'Waiting for targeted Sentry consumer heartbeats (%d/%d)...\n' "${attempt}" "${WAIT_ATTEMPTS}"
  fi
  sleep "${WAIT_DELAY}"
done

printf 'Initial targeted healthchecks are green; waiting %ss for one full healthcheck stability cycle...\n' "${STABILITY_DELAY}"
sleep "${STABILITY_DELAY}"

failures=0
for container in "${TARGETS[@]}"; do
  state="$(docker inspect "${container}" --format '{{.State.Status}}')"
  health="$(docker inspect "${container}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
  restarts="$(docker inspect "${container}" --format '{{.RestartCount}}')"
  printf '%s stable: state=%s health=%s restarts=%s\n' \
    "${container}" "${state}" "${health}" "${restarts}"
  if [[ "${state}" != "running" || "${health}" != "healthy" ]]; then
    failures=$((failures + 1))
    docker logs --tail 80 "${container}" >&2 2>/dev/null || true
  fi
done

if docker inspect "${KAFKA_CONTAINER}" >/dev/null 2>&1; then
  printf '\nKafka groups after recovery:\n'
  docker exec "${KAFKA_CONTAINER}" \
    kafka-consumer-groups --bootstrap-server kafka:9092 --list 2>/dev/null |
    grep -E 'snuba|replac|subscription|ingest-consumer|post-process-forwarder' || true

  required_groups=(
    ingest-consumer
    snuba-consumers
    snuba-group-attributes-consumers
    snuba-events-subscriptions-consumers
    snuba-replacers
    post-process-forwarder
  )
  for group in "${required_groups[@]}"; do
    group_detail="$(
      docker exec "${KAFKA_CONTAINER}" \
        kafka-consumer-groups \
        --bootstrap-server kafka:9092 \
        --describe \
        --group "${group}" 2>&1 || true
    )"
    printf '\n%s:\n%s\n' "${group}" "${group_detail}"
    if grep -Fq "does not exist" <<<"${group_detail}"; then
      printf '❌ Kafka consumer group was not recreated: %s\n' "${group}" >&2
      failures=$((failures + 1))
    fi
  done
fi

[[ "${failures}" -eq 0 ]] ||
  fail "targeted Sentry consumer recovery left ${failures} unhealthy Sentry consumer(s)"

printf '✅ targeted Sentry errors-only ingestion recovery converged\n'
printf 'Next: rerun diagnose-sentry.sh --check, then smoke-sentry-event.sh.\n'
