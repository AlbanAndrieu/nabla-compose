#!/usr/bin/env bash
# Read-only Sentry Kafka consumer readiness and bounded error categorization.
# No credentials, log bodies, offsets, migrations, restarts or Kafka queries.
set -euo pipefail

[[ "$#" -le 1 && "${1:---check}" == --check ]] || {
  printf 'usage: bash %s --check\n' "$0" >&2; exit 2;
}
command -v docker >/dev/null 2>&1 || {
  printf 'BLOCKED: Docker unavailable\n' >&2; exit 2;
}
# These are the two unhealthy services from the operator's latest readiness.
# Service names are fixed; no caller-supplied container selectors.
SERVICES=(sentry-events-consumer sentry-post-process-forwarder-errors)
PROJECT=ix-sentry
failed=0

for service in "${SERVICES[@]}"; do
  mapfile -t ids < <(docker ps -a \
    --filter "label=com.docker.compose.project=${PROJECT}" \
    --filter "label=com.docker.compose.service=${service}" \
    --format '{{.ID}}' 2>/dev/null || true)
  if (("${#ids[@]}" != 1)) || [[ ! "${ids[0]}" =~ ^[a-f0-9]{12,64}$ ]]; then
    printf 'BLOCKED service=%s container_count=%d (missing or ambiguous)\n' \
      "${service}" "${#ids[@]}" >&2
    failed=$((failed + 1))
    continue
  fi
  id="${ids[0]}"
  state="$(docker inspect --type container --format \
    '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.State.ExitCode}}|{{.RestartCount}}' \
    "${id}" 2>/dev/null || true)"
  IFS='|' read -r status health exit_code restarts <<<"${state}"
  case "${status}" in running|restarting|exited|created|dead) ;; *) status=unknown ;; esac
  case "${health}" in healthy|unhealthy|starting|none) ;; *) health=unknown ;; esac
  [[ "${exit_code}" =~ ^[0-9]+$ ]] || exit_code='-'
  [[ "${restarts}" =~ ^[0-9]+$ ]] || restarts='-'
  printf 'consumer=%s state=%s health=%s exit=%s restarts=%s\n' \
    "${service}" "${status}" "${health}" "${exit_code}" "${restarts}"
  if [[ "${status}" != running || "${health}" != healthy ]]; then
    failed=$((failed + 1))
    # Never show Docker output: messages sometimes include DSNs/tokens.
    docker logs --since 15m --tail 80 "${id}" 2>&1 |
      awk '{
        t=tolower($0); n++;
        if (t ~ /sesstmout|session timed out|group coordinator|rebalance/) kafka++;
        if (t ~ /kafka.*(timeout|connection refused|unavailable|failed)/) transport++;
        if (t ~ /redis.*(connection|timeout|denied)/) redis++;
        if (t ~ /clickhouse.*(connection|timeout|denied)/) clickhouse++;
        if (t ~ /traceback|fatal|uncaught|exception/) errors++;
      } END {
        printf "  recent_log_categories: sample=%d kafka_coordination=%d kafka_transport=%d redis=%d clickhouse=%d fatal=%d\n",
          n,kafka,transport,redis,clickhouse,errors;
      }' || true
  fi
done

if ((failed)); then
  printf 'BLOCKED: unhealthy_or_missing_consumers=%d; inspect bounded private diagnostic before any scoped recovery\n' "${failed}" >&2
  exit 1
fi
printf 'OK: both critical Sentry consumers running+healthy; separate E2E ingestion smoke still required\n'
