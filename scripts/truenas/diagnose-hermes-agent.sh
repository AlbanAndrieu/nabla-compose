#!/usr/bin/env bash
# shellcheck shell=bash
# Read-only TrueNAS/Hermes inventory. Never print Docker Config.Env or file contents.
set -euo pipefail

if [[ $# -gt 1 || "${1:---check}" != --check ]]; then
  echo 'Usage: bash scripts/truenas/diagnose-hermes-agent.sh [--check]' >&2
  exit 2
fi
for cmd in docker midclt jq curl stat grep; do
  command -v "${cmd}" >/dev/null 2>&1 || { printf 'ERROR missing=%s\n' "${cmd}" >&2; exit 2; }
done

APP_ID="${HERMES_APP_ID:-hermes-agent}"
CONTAINER="${HERMES_CONTAINER:-ix-hermes-agent-hermes-agent-1}"
LOKI_URL="${HERMES_LOKI_URL:-http://172.17.0.24:3100}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib/diagnostic-ui.sh
source "${ROOT}/scripts/lib/diagnostic-ui.sh"
diag_ui_init "${DIAG_COLOR:-auto}" "${DIAG_ICONS:-auto}" || exit 2

diag_section '1/3' 'TrueNAS application and Docker runtime (metadata only)'
app_state="$(midclt call app.query | jq -r --arg app "${APP_ID}" '[.[] | select(.id == $app or .name == $app) | .state][0] // "absent"')" || diag_fail 'TrueNAS app.query failed'
printf 'app=%s state=%s\n' "${APP_ID}" "${app_state:-unknown}"
[[ "${app_state}" == RUNNING ]] || diag_fail 'Hermes TrueNAS App is not RUNNING'

if docker inspect --type container "${CONTAINER}" >/dev/null 2>&1; then
  docker inspect --type container --format 'container={{.Name}} status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}not-defined{{end}} image={{.Config.Image}}' "${CONTAINER}"
  runtime_status="$(docker inspect --type container --format '{{.State.Status}}' "${CONTAINER}")"
  runtime_health="$(docker inspect --type container --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}not-defined{{end}}' "${CONTAINER}")"
  [[ "${runtime_status}" == running ]] || diag_fail "Hermes container status=${runtime_status:-unknown}"
  [[ "${runtime_health}" != unhealthy ]] || diag_fail 'Hermes container health=unhealthy'
  image_id="$(docker inspect --type container --format '{{.Image}}' "${CONTAINER}")"
  printf 'image_id=%s\n' "${image_id}"
  user="$(docker inspect --type container --format '{{.Config.User}}' "${CONTAINER}")"
  privileged="$(docker inspect --type container --format '{{.HostConfig.Privileged}}' "${CONTAINER}")"
  readonly="$(docker inspect --type container --format '{{.HostConfig.ReadonlyRootfs}}' "${CONTAINER}")"
  network="$(docker inspect --type container --format '{{.HostConfig.NetworkMode}}' "${CONTAINER}")"
  printf 'container_user=%s privileged=%s read_only_rootfs=%s network_mode=%s\n' "${user:-image-default-unknown}" "${privileged}" "${readonly}" "${network}"
  [[ "${privileged}" == false ]] || diag_fail 'Privileged container: unsuitable for chat gateway'
  [[ "${network}" != host ]] || diag_warn 'Host network: review isolation and binding'
  if [[ -z "${user}" || "${user}" == 0 || "${user}" == 0:* || "${user}" == root || "${user}" == root:* ]]; then
    diag_warn 'Non-root process identity not proven; verify process UID/GID separately'
  fi
  # Docker formats only mount destinations/flags. Host paths and content are never emitted.
  mounts="$(docker inspect --type container --format '{{range .Mounts}}{{printf "%s|%t\n" .Destination .RW}}{{end}}' "${CONTAINER}")"
  while IFS='|' read -r dest writable; do
    [[ -n "${dest}" ]] || continue
    case "${dest}" in
      /var/run/docker.sock|/run/docker.sock) diag_fail 'Docker socket mounted into Hermes (host-root equivalent)' ;;
      /mnt/cpool|/mnt/cpool/*) diag_warn "Host dataset mounted into Hermes: ${dest} writable=${writable}" ;;
    esac
  done <<< "${mounts}"
else
  diag_fail "Docker container ${CONTAINER} not found"
fi

diag_section '2/3' 'Environment source inventory (key presence only)'
for file in "${ROOT}/apps/hermes/.env" /mnt/cpool/hermes/.env /mnt/cpool/secrets/runtime/hermes/.env; do
  if [[ -f "${file}" ]]; then
    printf 'env_file=%s permissions=%s\n' "${file}" "$(stat -c '%a %U:%G' "${file}")"
    for key in TELEGRAM_BOT_TOKEN TELEGRAM_ALLOWED_USERS DISCORD_BOT_TOKEN DISCORD_ALLOWED_USERS GATEWAY_ALLOW_ALL_USERS HERMES_YOLO_MODE; do
      if grep -Eq "^[[:space:]]*(export[[:space:]]+)?${key}=" "${file}"; then
        printf 'key_present=%s source=%s\n' "${key}" "${file}"
      fi
    done
  else
    printf 'env_file_absent=%s\n' "${file}"
  fi
done

diag_section '3/3' 'Loki readiness (no log retrieval)'
if curl --fail --silent --show-error --connect-timeout 3 --max-time 7 "${LOKI_URL%/}/ready" >/dev/null 2>&1; then
  echo 'loki_ready=yes'
else
  diag_warn 'Loki readiness unreachable from this vantage point'
fi

diag_summary
((DIAG_FAILURES == 0))
