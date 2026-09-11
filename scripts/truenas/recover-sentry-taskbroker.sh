#!/usr/bin/env bash
set -euo pipefail

APP_ID="${SENTRY_APP_ID:-sentry}"
TASKBROKER_CONTAINER="${SENTRY_TASKBROKER_CONTAINER:-ix-sentry-taskbroker-1}"
TASKWORKER_CONTAINER="${SENTRY_TASKWORKER_CONTAINER:-ix-sentry-sentry-taskworker-1}"
KAFKA_CONTAINER="${SENTRY_KAFKA_CONTAINER:-ix-kafka-kafka-1}"
WAIT_ATTEMPTS="${SENTRY_TASKBROKER_RECOVERY_ATTEMPTS:-36}"
WAIT_DELAY="${SENTRY_TASKBROKER_RECOVERY_DELAY_SECONDS:-5}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "run with sudo"

for command in awk docker jq midclt; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

app_state="$(
  midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]" |
    jq -r '.[0].state // "MISSING"'
)"
[[ "${app_state}" == "RUNNING" ]] ||
  fail "TrueNAS app ${APP_ID} must be RUNNING before targeted Taskbroker recovery (current=${app_state})"

for container in "${TASKBROKER_CONTAINER}" "${TASKWORKER_CONTAINER}" "${KAFKA_CONTAINER}"; do
  docker inspect "${container}" >/dev/null 2>&1 || fail "required container is missing: ${container}"
done

taskbroker_state="$(docker inspect "${TASKBROKER_CONTAINER}" --format '{{.State.Status}}')"
[[ "${taskbroker_state}" == "running" ]] ||
  fail "Taskbroker is not running; run diagnose-sentry-taskbroker.sh instead of targeted recovery"

taskworker_state="$(docker inspect "${TASKWORKER_CONTAINER}" --format '{{.State.Status}}')"
taskworker_health="$(docker inspect "${TASKWORKER_CONTAINER}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
[[ "${taskworker_state}" == "running" ]] || fail "Sentry Taskworker is not running"
[[ "${taskworker_health}" == "healthy" ]] ||
  fail "Sentry Taskworker is not healthy (${taskworker_health}); diagnose before Taskbroker restart"

# A container restart reloads the bind-mounted Taskbroker config. Validate the
# live mount rather than assuming it matches the config the running process
# originally loaded. This specifically protects against a stale/unresolvable
# StatsD hostname turning a functional-but-stalled Taskbroker into a crash loop.
taskbroker_config_source="$(
  docker inspect "${TASKBROKER_CONTAINER}" |
    jq -r '.[0].Mounts[]? | select(.Destination == "/etc/taskbroker/config.yml") | .Source' |
    head -n1
)"

if [[ -n "${taskbroker_config_source}" && -f "${taskbroker_config_source}" ]]; then
  statsd_addr="$(
    awk '
      /^[[:space:]]*statsd_addr:[[:space:]]*/ {
        sub(/^[[:space:]]*statsd_addr:[[:space:]]*/, "")
        gsub(/["'\''[:space:]]/, "")
        print
        exit
      }
    ' "${taskbroker_config_source}"
  )"

  if [[ -n "${statsd_addr}" ]]; then
    statsd_host="${statsd_addr%:*}"
    statsd_port="${statsd_addr##*:}"
    printf 'taskbroker_live_config=%s\n' "${taskbroker_config_source}"
    printf 'taskbroker_statsd_addr=%s\n' "${statsd_addr}"

    case "${statsd_host}" in
      127.0.0.1|localhost|::1)
        ;;
      *)
        if ! docker exec \
          -e NABLA_STATSD_HOST="${statsd_host}" \
          -e NABLA_STATSD_PORT="${statsd_port}" \
          "${TASKWORKER_CONTAINER}" \
          python -c 'import os, socket; socket.getaddrinfo(os.environ["NABLA_STATSD_HOST"], int(os.environ["NABLA_STATSD_PORT"]))' \
          >/dev/null 2>&1; then
          fail "live Taskbroker statsd_addr ${statsd_addr} cannot be resolved from the Sentry network; refusing restart because Taskbroker metrics initialization would panic"
        fi
        ;;
    esac
  else
    printf 'taskbroker_live_config=%s statsd_addr=default\n' "${taskbroker_config_source}"
  fi
else
  printf 'WARN: could not identify readable live /etc/taskbroker/config.yml bind source; restart preflight cannot validate metrics destination\n' >&2
fi

get_group_detail() {
  docker exec "${KAFKA_CONTAINER}" \
    kafka-consumer-groups \
    --bootstrap-server kafka:9092 \
    --describe \
    --group taskworker 2>&1 || true
}

active_member_count() {
  awk '
    $1 == "taskworker" && $7 != "-" && $7 != "CONSUMER-ID" { count++ }
    END { print count + 0 }
  '
}

lag_sum() {
  awk '
    $1 == "taskworker" && $6 ~ /^[0-9]+$/ { lag += $6 }
    END { print lag + 0 }
  '
}

taskworker_can_reach_taskbroker() {
  docker exec "${TASKWORKER_CONTAINER}" \
    python -c 'import socket; s=socket.create_connection(("taskbroker", 50051), 3); s.close()' \
    >/dev/null 2>&1
}

before_detail="$(get_group_detail)"
printf 'Taskbroker targeted recovery preflight\n'
printf 'app=%s state=%s\n' "${APP_ID}" "${app_state}"
printf 'taskbroker=%s state=%s\n' "${TASKBROKER_CONTAINER}" "${taskbroker_state}"
printf 'taskworker=%s state=%s health=%s\n\n' \
  "${TASKWORKER_CONTAINER}" "${taskworker_state}" "${taskworker_health}"
printf 'Kafka taskworker group before recovery:\n%s\n' "${before_detail}"

if grep -Fq "does not exist" <<<"${before_detail}"; then
  fail "Kafka group taskworker does not exist; targeted restart cannot validate a rejoin"
fi

before_members="$(printf '%s\n' "${before_detail}" | active_member_count)"
before_lag="$(printf '%s\n' "${before_detail}" | lag_sum)"
printf 'before_members=%s before_lag=%s\n' "${before_members}" "${before_lag}"

[[ "${before_members}" -eq 0 ]] ||
  fail "taskworker already has ${before_members} active member(s); refusing an unnecessary Taskbroker restart"

printf '\nRestarting only %s...\n' "${TASKBROKER_CONTAINER}"
docker restart "${TASKBROKER_CONTAINER}" >/dev/null

rejoined=0
lag_decreased=0
rpc_reachable=0
after_members=0
after_lag="${before_lag}"
after_detail=""

for ((attempt = 1; attempt <= WAIT_ATTEMPTS; attempt++)); do
  state="$(docker inspect "${TASKBROKER_CONTAINER}" --format '{{.State.Status}}')"
  restart_count="$(docker inspect "${TASKBROKER_CONTAINER}" --format '{{.RestartCount}}')"
  exit_code="$(docker inspect "${TASKBROKER_CONTAINER}" --format '{{.State.ExitCode}}')"
  pid="$(docker inspect "${TASKBROKER_CONTAINER}" --format '{{.State.Pid}}')"

  case "${state}" in
    restarting|exited|dead)
      printf 'Taskbroker failed after targeted restart: state=%s restarts=%s pid=%s exit=%s\n' \
        "${state}" "${restart_count}" "${pid}" "${exit_code}" >&2
      docker logs --tail 160 "${TASKBROKER_CONTAINER}" >&2 2>/dev/null || true
      fail "Taskbroker entered ${state} after restart; repair its startup/configuration failure before Kafka consumer recovery"
      ;;
    running)
      ;;
    *)
      if ((attempt == 1 || attempt % 6 == 0)); then
        printf 'Waiting for Taskbroker container (%d/%d): state=%s restarts=%s pid=%s exit=%s\n' \
          "${attempt}" "${WAIT_ATTEMPTS}" "${state}" "${restart_count}" "${pid}" "${exit_code}"
      fi
      sleep "${WAIT_DELAY}"
      continue
      ;;
  esac

  if taskworker_can_reach_taskbroker; then
    rpc_reachable=1
  else
    rpc_reachable=0
  fi

  after_detail="$(get_group_detail)"
  after_members="$(printf '%s\n' "${after_detail}" | active_member_count)"
  after_lag="$(printf '%s\n' "${after_detail}" | lag_sum)"

  if [[ "${after_members}" -gt 0 ]]; then
    rejoined=1
  fi
  if [[ "${before_lag}" -eq 0 || "${after_lag}" -lt "${before_lag}" ]]; then
    lag_decreased=1
  fi

  if ((rpc_reachable == 1 && rejoined == 1 && lag_decreased == 1)); then
    break
  fi

  if ((attempt == 1 || attempt % 6 == 0)); then
    printf 'Waiting for functional recovery (%d/%d): rpc=%s members=%s lag=%s\n' \
      "${attempt}" "${WAIT_ATTEMPTS}" "${rpc_reachable}" "${after_members}" "${after_lag}"
  fi
  sleep "${WAIT_DELAY}"
done

printf '\nKafka taskworker group after recovery:\n%s\n' "${after_detail}"
printf 'taskbroker_rpc_reachable=%s after_members=%s after_lag=%s\n' \
  "${rpc_reachable}" "${after_members}" "${after_lag}"

if ((rpc_reachable == 0)); then
  docker logs --tail 160 "${TASKBROKER_CONTAINER}" >&2 2>/dev/null || true
  fail "Taskbroker restarted but Taskworker cannot reach taskbroker:50051; Docker health alone is not sufficient"
fi

if ((rejoined == 0)); then
  docker logs --tail 160 "${TASKBROKER_CONTAINER}" >&2 2>/dev/null || true
  fail "Taskbroker restarted but taskworker consumer membership did not recover"
fi

if ((lag_decreased == 0)); then
  docker logs --tail 160 "${TASKBROKER_CONTAINER}" >&2 2>/dev/null || true
  fail "Taskbroker rejoined but taskworker lag did not decrease from ${before_lag}"
fi

printf '\n✅ targeted Taskbroker recovery restored gRPC reachability, Kafka membership and backlog progress\n'
printf 'No Kafka offsets, topics or Taskbroker SQLite rows were modified.\n'
printf 'Next: run diagnose-sentry-taskbroker.sh, then smoke-sentry-event.sh.\n'
