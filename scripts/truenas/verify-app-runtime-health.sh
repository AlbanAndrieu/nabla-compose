#!/usr/bin/env bash
set -euo pipefail

APP_ID="${1:-}"
TIMEOUT_SECONDS="${NABLA_APP_HEALTH_TIMEOUT_SECONDS:-300}"
POLL_SECONDS="${NABLA_APP_HEALTH_POLL_SECONDS:-5}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ -n "${APP_ID}" ]] || fail "usage: $0 <app-id>"
for command in docker jq midclt; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

project="ix-${APP_ID}"
deadline=$((SECONDS + TIMEOUT_SECONDS))

while ((SECONDS < deadline)); do
  app_state="$(
    midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]" |
      jq -r 'if length == 1 then .[0].state else "MISSING" end'
  )"

  mapfile -t ids < <(
    docker ps -aq --filter "label=com.docker.compose.project=${project}"
  )

  if [[ "${app_state}" == "RUNNING" && ${#ids[@]} -gt 0 ]]; then
    failures=0
    pending=0
    running=0

    for id in "${ids[@]}"; do
      row="$(docker inspect "${id}" | jq -c '.[0] | {
        name:(.Name|ltrimstr("/")),
        status:(.State.Status // "unknown"),
        health:(.State.Health.Status // "none"),
        exit:(.State.ExitCode // 0),
        restart:(.RestartCount // 0)
      }')"
      status="$(jq -r '.status' <<<"${row}")"
      health="$(jq -r '.health' <<<"${row}")"
      exit_code="$(jq -r '.exit' <<<"${row}")"

      case "${status}" in
        running)
          running=$((running + 1))
          case "${health}" in
            healthy | none) ;;
            starting) pending=$((pending + 1)) ;;
            *) failures=$((failures + 1)) ;;
          esac
          ;;
        exited)
          # Accept successful one-shot initializers/migrations in a RUNNING App.
          if [[ "${exit_code}" != "0" ]]; then
            failures=$((failures + 1))
          fi
          ;;
        created | restarting)
          pending=$((pending + 1))
          ;;
        *)
          failures=$((failures + 1))
          ;;
      esac
    done

    if ((failures == 0 && pending == 0 && running > 0)); then
      printf 'OK: %s RUNNING with stable containers\n' "${APP_ID}"
      docker ps -a --filter "label=com.docker.compose.project=${project}"         --format '  {{.Names}}\t{{.Status}}'
      exit 0
    fi
  fi

  sleep "${POLL_SECONDS}"
done

printf 'ERROR: %s did not become stable within %ss\n' "${APP_ID}" "${TIMEOUT_SECONDS}" >&2
midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]" |
  jq 'if length == 1 then .[0] | {id,state,active_workloads} else . end' >&2 || true
docker ps -a --filter "label=com.docker.compose.project=${project}"   --format '  {{.Names}}\t{{.Status}}' >&2 || true
exit 1
