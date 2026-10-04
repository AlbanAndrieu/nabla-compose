#!/usr/bin/env bash
set -euo pipefail

# Shared compact/full diagnostic bootstrap.
NABLA_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/diagnostic.sh
source "$(dirname -- "${NABLA_SCRIPT_DIR}")/lib/diagnostic.sh"
nabla_diagnostic_maybe_wrap "${BASH_SOURCE[0]}" "$@"

APP_ID="${NPM_APP_ID:-nginx-proxy-manager}"
PROJECT="${NPM_COMPOSE_PROJECT:-ix-nginx-proxy-manager}"
ROOT="${NABLA_REPO_ROOT:-/mnt/cpool/compose/nabla-compose}"
COMPOSE="${ROOT}/apps/nginx-proxy-manager/compose.yml"
DATA_ROOT="${NPM_DATA_ROOT:-/mnt/cpool/npm}"
LETSENCRYPT_ROOT="${NPM_LETSENCRYPT_ROOT:-${ROOT}/apps/nginx-proxy-manager/letsencrypt}"
UI_URL="${NPM_UI_URL:-http://172.17.0.24:30021/}"
MODE="${1:---check}"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
usage: sudo bash scripts/truenas/diagnose-nginx-proxy-manager.sh [--check]

Read-only diagnosis for the legacy Nginx Proxy Manager TrueNAS Custom App.
It never starts/redeploys/stops containers and never prints container
environment variables or application database contents.
EOF
}

case "${MODE}" in
  --check) ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    fail "unknown mode: ${MODE}"
    ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run with sudo on TrueNAS"

for command in curl docker jq midclt stat; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ -f "${COMPOSE}" ]] || fail "missing repository Compose: ${COMPOSE}"

printf '==> repository Compose contract\n'
docker compose -f "${COMPOSE}" config --quiet --no-interpolate --no-env-resolution
printf '✅ Compose syntax is valid\n'

printf '\n==> TrueNAS application state\n'
app_json="$(midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]")"
if [[ "$(jq 'length' <<<"${app_json}")" -ne 1 ]]; then
  printf '❌ TrueNAS App is missing or ambiguous: %s\n' "${APP_ID}" >&2
  app_state="MISSING"
else
  app_state="$(jq -r '.[0].state // "UNKNOWN"' <<<"${app_json}")"
  jq '.[0] | {
    id,
    state,
    version,
    human_version,
    upgrade_available,
    active_workloads
  }' <<<"${app_json}"
fi

printf '\n==> recent lifecycle jobs (arguments intentionally omitted)\n'
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

printf '\n==> Docker runtime evidence\n'
mapfile -t container_ids < <(
  docker ps -a \
    --filter "label=com.docker.compose.project=${PROJECT}" \
    --format '{{.ID}}'
)
if [[ "${#container_ids[@]}" -eq 0 ]]; then
  mapfile -t container_ids < <(
    docker ps -a \
      --filter 'ancestor=jc21/nginx-proxy-manager:2.15.0' \
      --format '{{.ID}}'
  )
fi

runtime_fail=0
if [[ "${#container_ids[@]}" -eq 0 ]]; then
  printf '❌ no Docker container found for %s\n' "${APP_ID}" >&2
  runtime_fail=1
else
  for id in "${container_ids[@]}"; do
    docker inspect "${id}" |
      jq '.[0] | {
        name: (.Name | ltrimstr("/")),
        composeProject: .Config.Labels["com.docker.compose.project"],
        composeService: .Config.Labels["com.docker.compose.service"],
        state: .State.Status,
        health: (.State.Health.Status // "none"),
        exitCode: .State.ExitCode,
        restartCount: .RestartCount,
        startedAt: .State.StartedAt,
        finishedAt: .State.FinishedAt,
        ports: .NetworkSettings.Ports,
        mounts: [
          .Mounts[]
          | {
              type: .Type,
              source: .Source,
              destination: .Destination,
              rw: .RW
            }
        ]
      }'
    status="$(docker inspect -f '{{.State.Status}}' "${id}")"
    [[ "${status}" == "running" ]] || runtime_fail=1
  done
fi

printf '\n==> host port ownership\n'
docker ps --format '{{.Names}}\t{{.Ports}}' |
  grep -E '(^|[^0-9])(30020|30021|30022)->|:(30020|30021|30022)->' || true

printf '\n==> persistent path metadata\n'
for path in "${DATA_ROOT}" "${LETSENCRYPT_ROOT}"; do
  if [[ -e "${path}" ]]; then
    stat -c '%n owner=%U:%G mode=%a type=%F size=%s' "${path}"
  else
    printf '❌ missing path: %s\n' "${path}" >&2
    runtime_fail=1
  fi
done

if [[ -f "${DATA_ROOT}/database.sqlite" ]]; then
  stat -c 'database.sqlite owner=%U:%G mode=%a size=%s mtime=%y' \
    "${DATA_ROOT}/database.sqlite"
else
  printf '⚠️ %s/database.sqlite not found; verify the actual /data mount before migration\n' \
    "${DATA_ROOT}"
fi

printf '\n==> application-level UI probe\n'
http_code="$(
  curl --silent --show-error \
    --connect-timeout 3 \
    --max-time 8 \
    --output /dev/null \
    --write-out '%{http_code}' \
    "${UI_URL}" || true
)"
case "${http_code}" in
  2?? | 3??)
    printf '✅ Nginx Proxy Manager UI responded HTTP %s at %s\n' "${http_code}" "${UI_URL}"
    ;;
  *)
    printf '❌ Nginx Proxy Manager UI probe failed HTTP %s at %s\n' \
      "${http_code:-000}" "${UI_URL}" >&2
    runtime_fail=1
    ;;
esac

printf '\n==> diagnosis\n'
case "${app_state}" in
  RUNNING)
    if ((runtime_fail == 0)); then
      printf '✅ middleware, Docker runtime, storage paths and UI are coherent\n'
    else
      printf '❌ middleware says RUNNING but one or more runtime contracts failed\n' >&2
      exit 1
    fi
    ;;
  DEPLOYING)
    if ((runtime_fail == 0)); then
      printf '⚠️ middleware remains DEPLOYING while Docker/UI evidence is functional.\n'
      printf '   Inspect the lifecycle jobs above before any redeploy; this may be stale middleware lifecycle state.\n'
    else
      printf '❌ DEPLOYING correlates with a Docker/storage/UI failure; repair the failing contract before redeploy.\n' >&2
    fi
    exit 1
    ;;
  MISSING | STOPPED | CRASHED | ERROR)
    printf '❌ TrueNAS App state=%s; do not infer NPMplus cutover readiness from this legacy App failure.\n' "${app_state}" >&2
    exit 1
    ;;
  *)
    printf '❌ unexpected TrueNAS App state=%s\n' "${app_state}" >&2
    exit 1
    ;;
esac
