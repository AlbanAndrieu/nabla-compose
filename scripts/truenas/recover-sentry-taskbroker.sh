#!/usr/bin/env bash
set -euo pipefail

APP_ID="${SENTRY_APP_ID:-sentry}"
TASKBROKER_CONTAINER="${SENTRY_TASKBROKER_CONTAINER:-ix-sentry-taskbroker-1}"
TASKWORKER_CONTAINER="${SENTRY_TASKWORKER_CONTAINER:-ix-sentry-sentry-taskworker-1}"
KAFKA_CONTAINER="${SENTRY_KAFKA_CONTAINER:-ix-kafka-kafka-1}"
WAIT_ATTEMPTS="${SENTRY_TASKBROKER_RECOVERY_ATTEMPTS:-36}"
WAIT_DELAY="${SENTRY_TASKBROKER_RECOVERY_DELAY_SECONDS:-5}"
TASKBROKER_DEFAULT_STATSD_ADDR="127.0.0.1:8126"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "run with sudo"

for command in awk docker jq midclt; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

extract_yaml_statsd_addr() {
  local path="$1"
  awk '
    /^[[:space:]]*statsd_addr:[[:space:]]*/ {
      sub(/^[[:space:]]*statsd_addr:[[:space:]]*/, "")
      gsub(/["'"'"'[:space:]]/, "")
      print
      exit
    }
  ' "${path}"
}

validate_statsd_addr_from_taskworker() {
  local address="$1"
  docker exec \
    -e NABLA_STATSD_ADDR="${address}" \
    "${TASKWORKER_CONTAINER}" \
    python -c '
import os
import socket

address = os.environ["NABLA_STATSD_ADDR"]
if not address:
    raise SystemExit("empty StatsD address")

if address.startswith("["):
    host, separator, port = address[1:].partition("]:")
    if not separator:
        raise SystemExit(f"invalid bracketed StatsD address: {address}")
else:
    host, separator, port = address.rpartition(":")
    if not separator or not host:
        raise SystemExit(f"invalid StatsD address: {address}")

socket.getaddrinfo(host, int(port), type=socket.SOCK_DGRAM)
' >/dev/null 2>&1
}

app_state="$(
  midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]" |
    jq -r '.[0].state // "MISSING"'
)"
[[ "${app_state}" == "RUNNING" ]] ||
  fail "TrueNAS app ${APP_ID} must be RUNNING before targeted Taskbroker recovery (current=${app_state})"

for container in "${TASKBROKER_CONTAINER}" "${TASKWORKER_CONTAINER}" "${KAFKA_CONTAINER}"; do
  docker inspect "${container}" >/dev/null 2>&1 || fail "required container is missing: ${container}"
done

taskworker_state="$(docker inspect "${TASKWORKER_CONTAINER}" --format '{{.State.Status}}')"
taskworker_health="$(docker inspect "${TASKWORKER_CONTAINER}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
[[ "${taskworker_state}" == "running" ]] || fail "Sentry Taskworker is not running"
[[ "${taskworker_health}" == "healthy" ]] ||
  fail "Sentry Taskworker is not healthy (${taskworker_health}); diagnose before Taskbroker restart"

# Taskbroker merges defaults, YAML, then TASKBROKER_* environment variables.
# Reconstruct the effective StatsD destination before checking whether a restart
# is allowed. This keeps the current crash-loop diagnosable: an env override can
# supersede an otherwise safe bind-mounted YAML file.
taskbroker_config_source="$(
  docker inspect "${TASKBROKER_CONTAINER}" |
    jq -r '.[0].Mounts[]? | select(.Destination == "/etc/taskbroker/config.yml") | .Source' |
    head -n1
)"

yaml_statsd_addr=""
if [[ -n "${taskbroker_config_source}" && -f "${taskbroker_config_source}" ]]; then
  yaml_statsd_addr="$(extract_yaml_statsd_addr "${taskbroker_config_source}")"
else
  printf 'WARN: could not identify readable live /etc/taskbroker/config.yml bind source\n' >&2
fi

env_statsd_entry="$(
  docker inspect "${TASKBROKER_CONTAINER}" |
    jq -r '.[0].Config.Env[]? | select(startswith("TASKBROKER_STATSD_ADDR="))' |
    head -n1
)"

if [[ -n "${env_statsd_entry}" ]]; then
  effective_statsd_addr="${env_statsd_entry#*=}"
  statsd_source="environment:TASKBROKER_STATSD_ADDR"
elif [[ -n "${yaml_statsd_addr}" ]]; then
  effective_statsd_addr="${yaml_statsd_addr}"
  statsd_source="yaml:/etc/taskbroker/config.yml"
else
  effective_statsd_addr="${TASKBROKER_DEFAULT_STATSD_ADDR}"
  statsd_source="taskbroker-default"
fi

printf 'taskbroker_live_config=%s\n' "${taskbroker_config_source:-not-found}"
printf 'taskbroker_yaml_statsd_addr=%s\n' "${yaml_statsd_addr:-not-set}"
printf 'taskbroker_statsd_source=%s\n' "${statsd_source}"
printf 'taskbroker_effective_statsd_addr=%s\n' "${effective_statsd_addr:-<empty>}"

if ! validate_statsd_addr_from_taskworker "${effective_statsd_addr}"; then
  fail "effective Taskbroker StatsD address '${effective_statsd_addr:-<empty>}' from ${statsd_source} cannot be parsed/resolved from the Sentry network; refusing restart because metrics initialization would panic"
fi
printf 'taskbroker_statsd_resolution=ok\n'

taskbroker_state="$(docker inspect "${TASKBROKER_CONTAINER}" --format '{{.State.Status}}')"
case "${taskbroker_state}" in
  running)
    ;;
  restarting|exited|dead)
    restart_count="$(docker inspect "${TASKBROKER_CONTAINER}" --format '{{.RestartCount}}')"
    exit_code="$(docker inspect "${TASKBROKER_CONTAINER}" --format '{{.State.ExitCode}}')"
    pid="$(docker inspect "${TASKBROKER_CONTAINER}" --format '{{.State.Pid}}')"
    printf 'Taskbroker is not bootable: state=%s restarts=%s pid=%s exit=%s\n' \
      "${taskbroker_state}" "${restart_count}" "${pid}" "${exit_code}" >&2
    docker logs --tail 160 "${TASKBROKER_CONTAINER}" >&2 2>/dev/null || true
    fail "repair Taskbroker startup/configuration first; targeted Kafka recovery deliberately does not mutate config or whole-App state"
    ;;
  *)
    fail "Taskbroker is not running (state=${taskbroker_state}); run diagnose-sentry-taskbroker.sh first"
    ;;
esac

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
