#!/usr/bin/env bash
set -euo pipefail

# Keep interactive diagnostics compact while preserving full CI/non-TTY output.
if [[ "${NABLA_DIAGNOSTIC_WRAPPED:-0}" != "1" && "${DIAGNOSTIC_FULL_OUTPUT:-0}" != "1" && ( -t 1 || "${DIAGNOSTIC_COMPACT_OUTPUT:-0}" == "1" ) ]]; then
  NABLA_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  NABLA_DIAGNOSTIC_WRAPPER="$(dirname -- "${NABLA_SCRIPT_DIR}")/run-diagnostic.sh"
  exec "${NABLA_DIAGNOSTIC_WRAPPER}" \
    "${NABLA_SCRIPT_DIR}/$(basename -- "${BASH_SOURCE[0]}")" "$@"
fi

APP_ID="${SENTRY_TRUENAS_APP_ID:-sentry}"
PROJECT="${SENTRY_COMPOSE_PROJECT:-ix-sentry}"
EDGE_URL="${SENTRY_EDGE_HEALTH_URL:-http://172.17.0.24:9005/_health/}"
MODE="${1:---check}"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required"
}

usage() {
  cat <<'EOF'
Usage:
  bash scripts/truenas/diagnose-sentry.sh [--check]

This command is read-only. It inspects:
- TrueNAS app.query state
- recent app lifecycle jobs without printing their arguments
- Docker service state / health / restart counters
- one-shot migration exit codes
- Sentry edge health
- Snuba API health when the container is running

It never starts, stops, restarts, updates or redeploys the application.
EOF
}

case "${MODE}" in
  --check) ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    fail "unknown mode: ${MODE}"
    ;;
esac

for command in midclt jq docker curl; do
  require_command "${command}"
done

printf '==> TrueNAS Sentry application state\n'
app_json="$(
  midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]" '{"extra":{"retrieve_config":true}}'
)"
[[ "$(jq 'length' <<<"${app_json}")" -eq 1 ]] ||
  fail "TrueNAS application not found or ambiguous: ${APP_ID}"

app_state="$(jq -r '.[0].state // "UNKNOWN"' <<<"${app_json}")"
jq '.[0] | {
  id,
  state,
  version,
  human_version,
  upgrade_available,
  active_workloads
}' <<<"${app_json}"

printf '\n==> recent TrueNAS app lifecycle jobs\n'
midclt call core.get_jobs |
  jq --arg app "${APP_ID}" '
    [
      .[]
      | select((.method // "") | startswith("app."))
      | select(((.arguments // []) | tostring) | contains($app))
      | {
          id,
          method,
          state,
          progress: {
            percent: (.progress.percent // null),
            description: (.progress.description // null)
          },
          time_started,
          time_finished,
          error
        }
    ]
    | sort_by(.id)
    | reverse
    | .[:8]
  '

printf '\n==> Docker project containers\n'
mapfile -t container_ids < <(
  docker ps -a     --filter "label=com.docker.compose.project=${PROJECT}"     --format '{{.ID}}'
)

if [[ "${#container_ids[@]}" -eq 0 ]]; then
  fail "no containers found for Compose project ${PROJECT}"
fi

starting_count=0
unhealthy_count=0
unexpected_exit_count=0
one_shot_failure_count=0
kafka_topic_failure_count=0
kafka_topic_probe_available=0
session_timeout_detected=0
missing_subscription_group=0

for id in "${container_ids[@]}"; do
  inspect="$(docker inspect "${id}")"

  service="$(jq -r '.[0].Config.Labels["com.docker.compose.service"] // "unknown"' <<<"${inspect}")"
  name="$(jq -r '.[0].Name | ltrimstr("/")' <<<"${inspect}")"
  status="$(jq -r '.[0].State.Status // "unknown"' <<<"${inspect}")"
  health="$(jq -r '.[0].State.Health.Status // "none"' <<<"${inspect}")"
  exit_code="$(jq -r '.[0].State.ExitCode // 0' <<<"${inspect}")"
  restart_count="$(jq -r '.[0].RestartCount // 0' <<<"${inspect}")"
  started_at="$(jq -r '.[0].State.StartedAt // ""' <<<"${inspect}")"
  finished_at="$(jq -r '.[0].State.FinishedAt // ""' <<<"${inspect}")"

  printf '%-42s service=%-38s state=%-10s health=%-10s exit=%-3s restarts=%s\n'     "${name}" "${service}" "${status}" "${health}" "${exit_code}" "${restart_count}"
  printf '  started=%s finished=%s\n' "${started_at}" "${finished_at}"

  if [[ "${health}" != "none" ]]; then
    jq -r '
      .[0].State.Health as $h
      | "  health_failing_streak=\($h.FailingStreak // 0)"
    ' <<<"${inspect}"
    jq -r '
      .[0].State.Health.Log // []
      | .[-3:]
      | .[]
      | "  healthcheck start=\(.Start) exit=\(.ExitCode)"
    ' <<<"${inspect}"
  fi

  if [[ "${health}" == "unhealthy" ]]; then
    docker exec "${id}" sh -lc '
      if [ -e /tmp/health.txt ]; then
        stat -c "  heartbeat mtime=%y size=%s" /tmp/health.txt
      else
        printf "  heartbeat /tmp/health.txt currently absent\n"
      fi
    ' 2>/dev/null || true
    printf '  consumer_process:\n'
    docker exec "${id}" sh -lc \
      'ps -eo pid,etime,args | grep -v "[g]rep" | grep -E "(replacer|subscriptions-scheduler-executor|rust-consumer)"' \
      2>/dev/null || true
    for target in kafka:9092 redis:6379 sentry-clickhouse:9000; do
      host="${target%:*}"
      port="${target##*:}"
      if docker exec "${id}" python3 -c '
import socket
import sys
host = sys.argv[1]
port = int(sys.argv[2])
sock = socket.create_connection((host, port), 3)
sock.close()
' "${host}" "${port}" >/dev/null 2>&1; then
        printf '  ✅ %s -> %s\n' "${service}" "${target}"
      else
        printf '  ❌ %s -> %s\n' "${service}" "${target}" >&2
      fi
    done
    printf '  recent_diagnostic_logs:\n'
    diagnostic_logs="$(docker logs --since 24h "${id}" 2>&1 | tail -200 || true)"
    grep -Ei 'error|exception|traceback|kafka|clickhouse|redis|timeout|health|stuck|rebalance|partition|topic|coordinator'       <<<"${diagnostic_logs}" |
      tail -80 || true
    if grep -Eqi 'SESSTMOUT|session timed out|group coordinator' <<<"${diagnostic_logs}"; then
      session_timeout_detected=1
      printf '  ⚠️ Kafka consumer session/coordinator timeout detected in recent logs\n'
    fi
  fi

  case "${service}" in
    snuba-migrate|sentry-migrate)
      if [[ "${status}" == "exited" && "${exit_code}" -eq 0 ]]; then
        printf '  ✅ expected one-shot migration completed successfully\n'
      elif [[ "${status}" == "running" ]]; then
        printf '  ⚠️ expected one-shot migration is still running\n'
      else
        printf '  ❌ expected one-shot migration did not exit cleanly\n'
        one_shot_failure_count=$((one_shot_failure_count + 1))
      fi
      ;;
    *)
      if [[ "${status}" == "exited" ]]; then
        printf '  ❌ steady-state service is exited\n'
        unexpected_exit_count=$((unexpected_exit_count + 1))
      fi
      ;;
  esac

  case "${health}" in
    starting)
      starting_count=$((starting_count + 1))
      ;;
    unhealthy)
      unhealthy_count=$((unhealthy_count + 1))
      ;;
  esac
done

printf '\n==> Kafka topic contract\n'
required_topics=(
  events
  event-replacements
  snuba-commit-log
  scheduled-subscriptions-events
  events-subscription-results
)
kafka_container_id="$(
  docker ps \
    --filter 'label=com.docker.compose.service=kafka' \
    --format '{{.ID}}' |
    head -n 1
)"
if [[ -z "${kafka_container_id}" ]]; then
  kafka_container_id="$(
    docker ps \
      --filter 'ancestor=confluentinc/cp-kafka:7.6.6' \
      --format '{{.ID}}' |
      head -n 1
  )"
fi
if [[ -z "${kafka_container_id}" ]]; then
  printf '⚠️ shared Kafka runtime container could not be discovered\n'
elif docker exec "${kafka_container_id}" sh -lc 'command -v kafka-topics >/dev/null 2>&1'; then
  kafka_name="$(docker inspect "${kafka_container_id}" --format '{{.Name}}' | sed 's#^/##')"
  printf 'Kafka runtime container: %s\n' "${kafka_name}"
  kafka_topic_probe_available=1
  topics="$(
    docker exec "${kafka_container_id}" \
      kafka-topics --bootstrap-server kafka:9092 --list 2>/dev/null || true
  )"
  for topic in "${required_topics[@]}"; do
    if grep -Fxq "${topic}" <<<"${topics}"; then
      printf '✅ Kafka topic %s\n' "${topic}"
    else
      printf '❌ Kafka topic missing: %s\n' "${topic}" >&2
      kafka_topic_failure_count=$((kafka_topic_failure_count + 1))
    fi
  done
else
  kafka_name="$(docker inspect "${kafka_container_id}" --format '{{.Name}}' | sed 's#^/##')"
  printf '⚠️ kafka-topics CLI unavailable in shared Kafka container %s\n' "${kafka_name}"
fi

printf '\n==> unhealthy Kafka consumer-group evidence\n'
if [[ "${kafka_topic_probe_available}" -eq 1 ]]; then
  mapfile -t unhealthy_consumer_services < <(
    for id in "${container_ids[@]}"; do
      inspect="$(docker inspect "${id}")"
      service="$(jq -r '.[0].Config.Labels["com.docker.compose.service"] // ""' <<<"${inspect}")"
      health="$(jq -r '.[0].State.Health.Status // "none"' <<<"${inspect}")"
      if [[ "${health}" == "unhealthy" && ( "${service}" == snuba-* || "${service}" == "sentry-events-consumer" || "${service}" == "sentry-attachments-consumer" ) ]]; then
        printf '%s\n' "${service}"
      fi
    done
  )
  if [[ "${#unhealthy_consumer_services[@]}" -eq 0 ]]; then
    printf 'No unhealthy Sentry Kafka consumers require group inspection.\n'
  else
    printf 'Unhealthy Kafka consumer services: %s\n' "${unhealthy_consumer_services[*]}"
    printf 'Relevant Kafka consumer groups:\n'
    docker exec "${kafka_container_id}" kafka-consumer-groups --bootstrap-server kafka:9092 --list 2>/dev/null |
      grep -E 'snuba|replac|subscription' || true
    if printf '%s\n' "${unhealthy_consumer_services[@]}" | grep -Fxq 'snuba-subscription-consumer-events'; then
      printf '\nConsumer group snuba-events-subscriptions-consumers:\n'
      group_detail="$(
        docker exec "${kafka_container_id}" kafka-consumer-groups \
          --bootstrap-server kafka:9092 \
          --describe \
          --group snuba-events-subscriptions-consumers 2>&1 || true
      )"
      printf '%s\n' "${group_detail}"
      if grep -Fq "does not exist" <<<"${group_detail}"; then
        missing_subscription_group=1
      fi
    fi
    if printf '%s\n' "${unhealthy_consumer_services[@]}" |
      grep -Eq '^(sentry-events-consumer|sentry-attachments-consumer)$'; then
      printf '\nConsumer group ingest-consumer:\n'
      ingest_group_detail="$(
        docker exec "${kafka_container_id}" kafka-consumer-groups \
          --bootstrap-server kafka:9092 \
          --describe \
          --group ingest-consumer 2>&1 || true
      )"
      printf '%s\n' "${ingest_group_detail}"
      if grep -Fq "does not exist" <<<"${ingest_group_detail}"; then
        missing_subscription_group=1
      fi
    fi
    printf '\nNOTE: a running process with network connectivity but no /tmp/health.txt is not accepted as healthy.\n'
    printf 'The upstream Sentry compose uses the same heartbeat-file health contract for these Snuba consumers.\n'
  fi
else
  printf 'Kafka consumer-group inspection unavailable because kafka-consumer-groups was not discovered.\n'
fi

printf '\n==> Sentry functional edge health\n'
if curl --fail --silent --show-error --max-time 8 "${EDGE_URL}" >/dev/null; then
  printf '✅ Sentry edge healthy: %s\n' "${EDGE_URL}"
else
  printf '❌ Sentry edge health failed: %s\n' "${EDGE_URL}" >&2
  edge_failed=1
fi

printf '\n==> Snuba API health\n'
snuba_id="$(
  docker ps     --filter "label=com.docker.compose.project=${PROJECT}"     --filter 'label=com.docker.compose.service=snuba-api'     --format '{{.ID}}' |
  head -n 1
)"
if [[ -n "${snuba_id}" ]]; then
  if docker exec "${snuba_id}" python3 -c '
import urllib.request
body = urllib.request.urlopen("http://127.0.0.1:1218/health", timeout=3).read().decode()
raise SystemExit(0 if "ok" in body.lower() else 1)
' >/dev/null 2>&1; then
    printf '✅ Snuba API health is OK\n'
  else
    printf '❌ Snuba API health failed\n' >&2
    snuba_failed=1
  fi
else
  printf '❌ no running snuba-api container found\n' >&2
  snuba_failed=1
fi

printf '\n==> lifecycle diagnosis\n'
printf 'TrueNAS state=%s starting_health=%d unhealthy=%d unexpected_exited=%d one_shot_failures=%d kafka_topic_failures=%d\n' \
  "${app_state}" "${starting_count}" "${unhealthy_count}" \
  "${unexpected_exit_count}" "${one_shot_failure_count}" "${kafka_topic_failure_count}"
if ((kafka_topic_probe_available == 0)); then
  printf '⚠️ Kafka topic verification was unavailable; connectivity checks remain diagnostic evidence only.\n'
fi

if ((unhealthy_count > 0 && missing_subscription_group > 0)); then
  printf '⚠️ Unhealthy Sentry consumers currently have a missing Kafka consumer group.\n'
  printf '   Do not redeploy the whole Sentry app. Run the targeted recovery helper:\n'
  printf '   sudo bash scripts/truenas/recover-sentry-snuba-consumers.sh\n'
  printf '   Then rerun diagnose-sentry.sh --check.\n'
elif ((unhealthy_count > 0 && session_timeout_detected > 0)); then
  printf '⚠️ Unhealthy Sentry consumers have recent Kafka session/coordinator timeout evidence.\n'
  printf '   The group currently exists, so inspect the current heartbeat/group assignment before restarting again.\n'
elif ((unhealthy_count == 0 && session_timeout_detected > 0)); then
  printf 'ℹ️ Historical Kafka session timeout evidence exists, but no Sentry Kafka consumer is currently unhealthy.\n'
fi

if [[ "${app_state}" == "DEPLOYING" && "${starting_count}" -gt 0 ]]; then
  printf '⚠️ TrueNAS DEPLOYING correlates with containers whose Docker health is still "starting".\n'
  printf '   Sentry/Snuba consumer healthchecks intentionally allow a 600-second first-start grace.\n'
  printf '   Do not repeatedly redeploy during that window: it resets healthcheck convergence and makes diagnosis harder.\n'
  printf '   Inspect the named services above first; for Sentry 26.8 consumers this usually means the /tmp/health.txt heartbeat has not yet produced a successful Docker healthcheck.\n'
elif [[ "${app_state}" == "DEPLOYING" && "${starting_count}" -eq 0 && "${unhealthy_count}" -eq 0 ]]; then
  printf '⚠️ TrueNAS is DEPLOYING while Docker exposes no starting/unhealthy healthcheck.\n'
  printf '   Inspect the recent app lifecycle jobs above for a stuck/failed middleware lifecycle operation or stale app state.\n'
fi

if [[ "${app_state}" != "RUNNING" ]]; then
  exit 1
fi
if [[ "${unhealthy_count}" -gt 0 ]]; then
  exit 1
fi
if [[ "${unexpected_exit_count}" -gt 0 ]]; then
  exit 1
fi
if [[ "${one_shot_failure_count}" -gt 0 ]]; then
  exit 1
fi
if [[ "${kafka_topic_failure_count}" -gt 0 ]]; then
  exit 1
fi
if [[ "${edge_failed:-0}" -ne 0 ]]; then
  exit 1
fi
if [[ "${snuba_failed:-0}" -ne 0 ]]; then
  exit 1
fi

printf '✅ Sentry TrueNAS lifecycle and functional health are converged\n'
