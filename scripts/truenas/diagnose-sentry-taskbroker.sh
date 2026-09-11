#!/usr/bin/env bash
set -euo pipefail

TASKBROKER_CONTAINER="${SENTRY_TASKBROKER_CONTAINER:-ix-sentry-taskbroker-1}"
TASKWORKER_CONTAINER="${SENTRY_TASKWORKER_CONTAINER:-ix-sentry-sentry-taskworker-1}"
KAFKA_CONTAINER="${SENTRY_KAFKA_CONTAINER:-ix-kafka-kafka-1}"
TASKBROKER_DB="${SENTRY_TASKBROKER_DB:-/mnt/cpool/sentry/taskbroker/taskbroker-activations.sqlite}"
STATSD_METRICS_URL="${SENTRY_STATSD_METRICS_URL:-http://172.17.0.24:9102/metrics}"
KAFKA_EXPORTER_URL="${SENTRY_KAFKA_EXPORTER_URL:-http://172.17.0.24:9308/metrics}"

for command in curl docker python3; do
  command -v "${command}" >/dev/null 2>&1 || {
    printf 'ERROR: %s is required\n' "${command}" >&2
    exit 1
  }
done

printf 'Sentry taskbroker diagnostic (read-only)\n'
printf 'db=%s\n' "${TASKBROKER_DB}"
printf 'statsd_metrics=%s\n' "${STATSD_METRICS_URL}"
printf 'kafka_exporter=%s\n\n' "${KAFKA_EXPORTER_URL}"

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

printf '=== Prometheus exporter correlation ===\n'
printf '%s\n' '-- Taskbroker / Sentry StatsD --'
if statsd_metrics="$(curl -fsS --max-time 5 "${STATSD_METRICS_URL}" 2>/dev/null)"; then
  printf '%s\n' "${statsd_metrics}" |
    grep -E '^(taskbroker_|sentry_taskworker_|statsd_exporter_)' |
    head -n 160 || true
else
  printf 'UNAVAILABLE: %s\n' "${STATSD_METRICS_URL}"
fi

printf '\n%s\n' '-- Kafka taskworker group --'
if kafka_metrics="$(curl -fsS --max-time 10 "${KAFKA_EXPORTER_URL}" 2>/dev/null)"; then
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
