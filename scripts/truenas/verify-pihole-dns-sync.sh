#!/usr/bin/env bash
set -euo pipefail

SYNC_CONTAINER="${NABLA_PIHOLE_SYNC_CONTAINER:-pihole-dns-sync}"
PIHOLE_CONTAINER="${NABLA_PIHOLE_CONTAINER:-pihole}"
NETWORK="${NABLA_DOCKER_PROXY_NETWORK:-intranet}"
PROXY_ALIAS="${NABLA_DOCKER_PROXY_ALIAS:-docker-socket-proxy}"
EXPECTED_MAX_SESSIONS="${NABLA_PIHOLE_EXPECTED_MAX_SESSIONS:-16}"
TIMEOUT_SECONDS="${NABLA_PIHOLE_SYNC_TIMEOUT_SECONDS:-60}"
POLL_SECONDS="${NABLA_PIHOLE_SYNC_POLL_SECONDS:-2}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "run as root"
for command in docker grep jq; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done
for value in TIMEOUT_SECONDS POLL_SECONDS EXPECTED_MAX_SESSIONS; do
  current="${!value}"
  [[ "${current}" =~ ^[1-9][0-9]*$ ]] || fail "${value} must be a positive integer"
done

for container in "${PIHOLE_CONTAINER}" "${SYNC_CONTAINER}"; do
  docker inspect "${container}" >/dev/null 2>&1 ||
    fail "container not found: ${container}"
done

deadline=$((SECONDS + TIMEOUT_SECONDS))
while ((SECONDS < deadline)); do
  sync_state="$(
    docker inspect "${SYNC_CONTAINER}" |
      jq -c --arg network "${NETWORK}" '.[0] | {
        status:(.State.Status // "unknown"),
        running:(.State.Running // false),
        restarting:(.State.Restarting // false),
        restarts:(.RestartCount // 0),
        started:(.State.StartedAt // ""),
        network:(.NetworkSettings.Networks[$network] // null)
      }'
  )"

  [[ "$(jq -r '.running' <<<"${sync_state}")" == "true" ]] ||
    fail "${SYNC_CONTAINER}: not running"
  [[ "$(jq -r '.restarting' <<<"${sync_state}")" == "false" ]] ||
    fail "${SYNC_CONTAINER}: restart loop detected"
  [[ "$(jq -r '.network' <<<"${sync_state}")" != "null" ]] ||
    fail "${SYNC_CONTAINER}: not attached to ${NETWORK}"

  if ! docker exec "${SYNC_CONTAINER}" getent hosts "${PROXY_ALIAS}" >/dev/null 2>&1; then
    fail "${SYNC_CONTAINER}: cannot resolve ${PROXY_ALIAS} through Docker DNS"
  fi

  started_at="$(jq -r '.started' <<<"${sync_state}")"
  recent_logs="$(docker logs --since "${started_at}" "${SYNC_CONTAINER}" 2>&1 || true)"

  if grep -Eq     'api_seats_exceeded|Failed to authenticate|Could not authenticate|no such host|failed to connect to the docker API'     <<<"${recent_logs}"; then
    printf '%s\n' "${recent_logs}" >&2
    fail "${SYNC_CONTAINER}: current-start logs contain DNS/Docker/Pi-hole API failure"
  fi

  if grep -Fq 'Initial sync done' <<<"${recent_logs}"; then
    break
  fi

  sleep "${POLL_SECONDS}"
done

if ! grep -Fq 'Initial sync done' <<<"${recent_logs:-}"; then
  fail "${SYNC_CONTAINER}: Initial sync did not complete within ${TIMEOUT_SECONDS}s"
fi

actual_sessions="$(
  docker exec "${PIHOLE_CONTAINER}"     pihole-FTL --config webserver.api.max_sessions 2>/dev/null |
    tail -n1 | tr -d '[:space:]'
)"
[[ "${actual_sessions}" == "${EXPECTED_MAX_SESSIONS}" ]] ||
  fail "${PIHOLE_CONTAINER}: webserver.api.max_sessions=${actual_sessions:-unknown}, expected=${EXPECTED_MAX_SESSIONS}"

env_sessions="$(
  docker inspect "${PIHOLE_CONTAINER}" |
    jq -r '
      .[0].Config.Env // []
      | map(select(startswith("FTLCONF_webserver_api_max_sessions=")))
      | first // ""
    '
)"
expected_env="FTLCONF_webserver_api_max_sessions=${EXPECTED_MAX_SESSIONS}"
[[ "${env_sessions}" == "${expected_env}" ]] ||
  fail "${PIHOLE_CONTAINER}: expected runtime env ${expected_env}, got ${env_sessions:-missing}"

restarts="$(jq -r '.restarts' <<<"${sync_state}")"
if [[ "${restarts}" != "0" ]]; then
  printf 'WARN: %s restart_count=%s; current start is healthy but review previous failures\n'     "${SYNC_CONTAINER}" "${restarts}" >&2
fi

resolved="$(docker exec "${SYNC_CONTAINER}" getent hosts "${PROXY_ALIAS}" | head -n1)"
printf 'OK: Pi-hole DNS sync healthy; proxy=%s max_sessions=%s\n'   "${resolved}" "${actual_sessions}"
