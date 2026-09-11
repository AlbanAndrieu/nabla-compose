#!/usr/bin/env bash
set -euo pipefail

TASKBROKER_CONTAINER="${SENTRY_TASKBROKER_CONTAINER:-ix-sentry-taskbroker-1}"
TASKWORKER_CONTAINER="${SENTRY_TASKWORKER_CONTAINER:-ix-sentry-sentry-taskworker-1}"
KAFKA_CONTAINER="${SENTRY_KAFKA_CONTAINER:-ix-kafka-kafka-1}"
TASKBROKER_DB="${SENTRY_TASKBROKER_DB:-/mnt/cpool/sentry/taskbroker/taskbroker-activations.sqlite}"
STATSD_METRICS_URL="${SENTRY_STATSD_METRICS_URL:-}"
KAFKA_EXPORTER_URL="${SENTRY_KAFKA_EXPORTER_URL:-}"
TASKBROKER_DEFAULT_STATSD_ADDR="127.0.0.1:8126"

for command in awk curl docker jq python3; do
  command -v "${command}" >/dev/null 2>&1 || {
    printf 'ERROR: %s is required\n' "${command}" >&2
    exit 1
  }
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

printf 'Sentry taskbroker diagnostic (read-only)\n'
printf 'db=%s\n' "${TASKBROKER_DB}"
printf 'statsd_metrics=%s\n' "${STATSD_METRICS_URL:-not-configured}"
printf 'kafka_exporter=%s\n\n' "${KAFKA_EXPORTER_URL:-not-configured}"

printf '=== Taskbroker effective startup inputs ===\n'
if ! docker inspect "${TASKBROKER_CONTAINER}" >/dev/null 2>&1; then
  printf 'MISSING: %s\n\n' "${TASKBROKER_CONTAINER}"
else
  docker inspect "${TASKBROKER_CONTAINER}" --format \
    'image={{.Config.Image}} image_id={{.Image}} state={{.State.Status}} restarts={{.RestartCount}} pid={{.State.Pid}} exit={{.State.ExitCode}} error={{.State.Error}}'

  taskbroker_config_source="$(
    docker inspect "${TASKBROKER_CONTAINER}" |
      jq -r '.[0].Mounts[]? | select(.Destination == "/etc/taskbroker/config.yml") | .Source' |
      head -n1
  )"
  printf 'taskbroker_live_config=%s\n' "${taskbroker_config_source:-not-found}"

  yaml_statsd_addr=""
  if [[ -n "${taskbroker_config_source}" && -f "${taskbroker_config_source}" ]]; then
    yaml_statsd_addr="$(extract_yaml_statsd_addr "${taskbroker_config_source}")"
    printf 'taskbroker_yaml_statsd_addr=%s\n' "${yaml_statsd_addr:-not-set}"
  else
    printf 'taskbroker_yaml_statsd_addr=unknown\n'
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

  printf 'taskbroker_statsd_source=%s\n' "${statsd_source}"
  printf 'taskbroker_effective_statsd_addr=%s\n' "${effective_statsd_addr:-<empty>}"

  if docker inspect "${TASKWORKER_CONTAINER}" >/dev/null 2>&1; then
    if validate_statsd_addr_from_taskworker "${effective_statsd_addr}"; then
      printf 'taskbroker_statsd_resolution=ok\n'
    else
      printf 'taskbroker_statsd_resolution=FAILED\n'
      printf 'WARN: effective Taskbroker StatsD address cannot be parsed/resolved from the Sentry network; this can reproduce the metrics.rs boot panic\n' >&2
    fi

    if docker exec "${TASKWORKER_CONTAINER}" \
      python -c 'import socket; s=socket.create_connection(("taskbroker", 50051), 3); s.close()' \
      >/dev/null 2>&1; then
      printf 'taskbroker_rpc_from_taskworker=reachable\n'
    else
      printf 'taskbroker_rpc_from_taskworker=UNAVAILABLE\n'
    fi
  else
    printf 'taskbroker_statsd_resolution=unknown-taskworker-missing\n'
    printf 'taskbroker_rpc_from_taskworker=unknown-taskworker-missing\n'
  fi
  printf '\n'
fi

for container in "${TASKBROKER_CONTAINER}" "${TASKWORKER_CONTAINER}"; do
  printf '=== %s ===\n' "${container}"
  if ! docker inspect "${container}" >/dev/null 2>&1; then
    printf 'MISSING\n\n'
    continue
  fi
  docker inspect "${container}" --format \
    'state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} restarts={{.RestartCount}} pid={{.State.Pid}} exit={{.State.ExitCode}} error={{.State.Error}}'
  printf 'command='
  docker inspect "${container}" --format '{{json .Config.Cmd}}'
  printf '\nRecent logs:\n'
  docker logs --tail 120 "${container}" 2>&1 || true
  printf '\n'
done

printf '=== Kafka taskworker topic/group ===\n'
if docker inspect "${KAFKA_CONTAINER}" >/dev/null 2>&1; then
  docker exec "${KAFKA_CONTAINER}" kafka-topics \
    --bootstrap-server kafka:9092 \
    --describe \
    --topic taskworker 2>&1 || true
  printf '\n'
  docker exec "${KAFKA_CONTAINER}" kafka-consumer-groups \
    --bootstrap-server kafka:9092 \
    --describe \
    --group taskworker 2>&1 || true
else
  printf 'Kafka container missing: %s\n' "${KAFKA_CONTAINER}"
fi
printf '\n'

printf '=== Optional exporter correlation ===\n'
printf '%s\n' '-- Taskbroker / Sentry StatsD --'
if [[ -z "${STATSD_METRICS_URL}" ]]; then
  printf 'SKIPPED: SENTRY_STATSD_METRICS_URL is not configured\n'
elif statsd_metrics="$(curl -fsS --max-time 5 "${STATSD_METRICS_URL}" 2>/dev/null)"; then
  printf '%s\n' "${statsd_metrics}" |
    grep -E '^(taskbroker_|sentry_taskworker_|statsd_exporter_)' |
    head -n 160 || true
else
  printf 'UNAVAILABLE: %s\n' "${STATSD_METRICS_URL}"
fi

printf '\n%s\n' '-- Kafka taskworker group exporter --'
if [[ -z "${KAFKA_EXPORTER_URL}" ]]; then
  printf 'SKIPPED: SENTRY_KAFKA_EXPORTER_URL is not configured\n'
elif kafka_metrics="$(curl -fsS --max-time 10 "${KAFKA_EXPORTER_URL}" 2>/dev/null)"; then
  printf '%s\n' "${kafka_metrics}" |
    grep -E '^kafka_consumergroup_(members|lag|current_offset)' |
    grep 'consumergroup="taskworker"' |
    head -n 120 || true
else
  printf 'UNAVAILABLE: %s\n' "${KAFKA_EXPORTER_URL}"
fi
printf '\n'

printf '=== Taskbroker SQLite ===\n'
if [[ ! -f "${TASKBROKER_DB}" ]]; then
  printf 'MISSING: %s\n' "${TASKBROKER_DB}"
else
  TASKBROKER_DB="${TASKBROKER_DB}" python3 - <<'PY'
import os
import sqlite3

path = os.environ["TASKBROKER_DB"]
con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
cur = con.cursor()

tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("tables:", ", ".join(tables) or "none")

if "inflight_taskactivations" not in tables:
    print("inflight_taskactivations: MISSING")
    raise SystemExit(0)

columns = [r[1] for r in cur.execute("PRAGMA table_info(inflight_taskactivations)")]
print("columns:", ", ".join(columns))
print("total:", cur.execute("SELECT count(*) FROM inflight_taskactivations").fetchone()[0])

for column in ("application", "status", "taskname", "topic", "bucket"):
    if column not in columns:
        continue
    print(f"\nby_{column}:")
    query = f'''SELECT COALESCE(CAST({column} AS TEXT), '<NULL>'), count(*)
                FROM inflight_taskactivations
                GROUP BY {column}
                ORDER BY count(*) DESC
                LIMIT 30'''
    for value, count in cur.execute(query):
        print(f"  {value!r}: {count}")

if "application" in columns:
    empty = cur.execute(
        "SELECT count(*) FROM inflight_taskactivations WHERE application IS NULL OR application = ''"
    ).fetchone()[0]
    sentry = cur.execute(
        "SELECT count(*) FROM inflight_taskactivations WHERE application = 'sentry'"
    ).fetchone()[0]
    print(f"\napplication_empty={empty}")
    print(f"application_sentry={sentry}")
    if empty:
        print("WARN: legacy/empty application task activations exist; this matches the known 25.x -> 26.x taskworker compatibility failure pattern")

if "received_at" in columns:
    row = cur.execute("SELECT min(received_at), max(received_at) FROM inflight_taskactivations").fetchone()
    print(f"received_at_min={row[0]} received_at_max={row[1]}")

con.close()
PY
fi

printf '\nREAD-ONLY: no Kafka offsets, SQLite rows, containers or TrueNAS App state changed.\n'
