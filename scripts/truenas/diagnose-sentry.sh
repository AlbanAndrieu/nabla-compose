#!/usr/bin/env bash
set -euo pipefail

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

(("${#container_ids[@]}" > 0)) ||
  fail "no containers found for Compose project ${PROJECT}"

starting_count=0
unhealthy_count=0
unexpected_exit_count=0
one_shot_failure_count=0

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
printf 'TrueNAS state=%s starting_health=%d unhealthy=%d unexpected_exited=%d one_shot_failures=%d\n'   "${app_state}" "${starting_count}" "${unhealthy_count}"   "${unexpected_exit_count}" "${one_shot_failure_count}"

if [[ "${app_state}" == "DEPLOYING" && "${starting_count}" -gt 0 ]]; then
  printf '⚠️ TrueNAS DEPLOYING correlates with containers whose Docker health is still "starting".\n'
  printf '   Inspect the named services above first; for Sentry 26.8 consumers this usually means the /tmp/health.txt heartbeat has not yet produced a successful Docker healthcheck.\n'
elif [[ "${app_state}" == "DEPLOYING" && "${starting_count}" -eq 0 && "${unhealthy_count}" -eq 0 ]]; then
  printf '⚠️ TrueNAS is DEPLOYING while Docker exposes no starting/unhealthy healthcheck.\n'
  printf '   Inspect the recent app lifecycle jobs above for a stuck/failed middleware lifecycle operation or stale app state.\n'
fi

if [[ "${app_state}" != "RUNNING" ]] ||
   ((unhealthy_count > 0)) ||
   ((unexpected_exit_count > 0)) ||
   ((one_shot_failure_count > 0)) ||
   [[ "${edge_failed:-0}" -ne 0 ]] ||
   [[ "${snuba_failed:-0}" -ne 0 ]]; then
  exit 1
fi

printf '✅ Sentry TrueNAS lifecycle and functional health are converged\n'
