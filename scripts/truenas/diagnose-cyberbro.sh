#!/usr/bin/env bash
set -euo pipefail

APP_ID="${CYBERBRO_APP_ID:-cyberbro}"
CYBERBRO_URL="${CYBERBRO_URL:-http://172.17.0.24:5100/}"
MCP_URL="${CYBERBRO_MCP_URL:-http://172.17.0.24:8013/mcp}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

for command in midclt jq docker curl; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

printf '==> TrueNAS application state\n'
app_json="$(midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]")"
[[ "$(jq 'length' <<<"${app_json}")" -eq 1 ]] || fail "TrueNAS application ${APP_ID} not found or ambiguous"
app_state="$(jq -r '.[0].state // "UNKNOWN"' <<<"${app_json}")"
jq '.[0] | {id,state,version,human_version,active_workloads}' <<<"${app_json}"

printf '\n==> recent TrueNAS app jobs (arguments omitted)\n'
midclt call core.get_jobs |
  jq --arg app "${APP_ID}" '[.[] | select((.method // "") | startswith("app.")) | select(((.arguments // []) | tostring) | contains($app)) | {id,method,state,progress:{percent:(.progress.percent // null),description:(.progress.description // null)},time_started,time_finished,error}] | sort_by(.id) | reverse | .[:8]'

failed=0
printf '\n==> Docker state\n'
for name in cyberbro mcp-cyberbro; do
  if ! docker inspect "${name}" >/dev/null 2>&1; then
    printf 'ERROR: container missing: %s\n' "${name}" >&2
    failed=1
    continue
  fi
  inspect="$(docker inspect "${name}")"
  status="$(jq -r '.[0].State.Status // "unknown"' <<<"${inspect}")"
  health="$(jq -r '.[0].State.Health.Status // "none"' <<<"${inspect}")"
  restarts="$(jq -r '.[0].RestartCount // 0' <<<"${inspect}")"
  printf '%-16s state=%-10s health=%-10s restarts=%s\n' "${name}" "${status}" "${health}" "${restarts}"
  if [[ "${status}" != "running" || ( "${name}" == "cyberbro" && "${health}" != "healthy" ) ]]; then
    failed=1
  fi
done

printf '\n==> database dependency\n'
printf 'INFO: Cyberbro has no database dependency in the repository Compose contract.\n'

printf '\n==> functional probes\n'
curl -fsS --max-time 8 -o /dev/null "${CYBERBRO_URL}" || failed=1
curl -sS --max-time 8 -o /dev/null "${MCP_URL}" || failed=1
[[ "${app_state}" == "RUNNING" ]] || failed=1

if ((failed > 0)); then
  printf '\n==> bounded container logs (review locally; do not paste secrets)\n'
  for name in cyberbro mcp-cyberbro; do
    docker logs --tail 80 "${name}" 2>&1 | tail -80 || true
  done

  printf '\n==> bounded middleware evidence\n'
  if [[ -r /var/log/middlewared.log ]]; then
    grep -Ei 'cyberbro|app\.(create|update|redeploy)|docker|compose' /var/log/middlewared.log | tail -80 || true
  fi

  if command -v journalctl >/dev/null 2>&1; then
    printf '\n==> bounded Docker service evidence\n'
    journalctl -u docker --since '-15 min' --no-pager 2>/dev/null | tail -80 || true

    printf '\n==> bounded system warning evidence\n'
    journalctl --since '-15 min' -p warning..alert --no-pager 2>/dev/null |
      grep -Ei 'cyberbro|docker|middleware|zfs|ix-app' |
      tail -80 || true
  fi

  fail "Cyberbro runtime diagnosis failed"
fi

printf 'OK: Cyberbro runtime diagnosis passed.\n'
