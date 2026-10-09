#!/usr/bin/env bash
set -euo pipefail

APP_ID="${CYBERBRO_APP_ID:-cyberbro}"
CYBERBRO_URL="${CYBERBRO_URL:-http://172.17.0.24:5100/}"
MCP_URL="${CYBERBRO_MCP_URL:-http://172.17.0.24:8013/mcp}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
VERBOSE="${CYBERBRO_DIAGNOSTIC_VERBOSE:-false}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

for command in midclt jq docker curl; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

# shellcheck source=../lib/truenas.sh
source "${ROOT}/scripts/lib/truenas.sh"

printf '==> Cyberbro runtime summary\n'
app_json="$(truenas_app_query_by_id "${APP_ID}")"
[[ "$(jq 'length' <<<"${app_json}")" -eq 1 ]] || fail "TrueNAS application ${APP_ID} not found or ambiguous"
app_state="$(jq -r '.[0].state // "UNKNOWN"' <<<"${app_json}")"
container_count="$(jq -r '.[0].active_workloads.containers // 0' <<<"${app_json}")"
printf 'TrueNAS app=%s state=%s containers=%s\n' "${APP_ID}" "${app_state}" "${container_count}"

lifecycle_warning=0
if [[ -n "${TRUENAS_LIFECYCLE_MARK:-}" ]]; then
  lifecycle_mark="${TRUENAS_LIFECYCLE_MARK}"
else
  lifecycle_lines="$(truenas_lifecycle_mark)"
  if [[ "${lifecycle_lines}" =~ ^[0-9]+$ ]] && ((lifecycle_lines > 500)); then
    lifecycle_mark=$((lifecycle_lines - 500))
  else
    lifecycle_mark=0
  fi
fi
if ! truenas_lifecycle_errors_since "${APP_ID}" "${lifecycle_mark}" 20; then
  lifecycle_warning=1
fi

failed=0
declare -A container_ids=()
printf '\n==> Compose services\n'
for service in cyberbro mcp-cyberbro; do
  container_id="$(truenas_compose_container_id "${APP_ID}" "${service}")"
  container_ids["${service}"]="${container_id}"
  if [[ -z "${container_id}" ]]; then
    printf 'ERROR: Compose service container missing: %s\n' "${service}" >&2
    failed=1
    continue
  fi
  inspect="$(docker inspect "${container_id}")"
  status="$(jq -r '.[0].State.Status // "unknown"' <<<"${inspect}")"
  health="$(jq -r '.[0].State.Health.Status // "none"' <<<"${inspect}")"
  restarts="$(jq -r '.[0].RestartCount // 0' <<<"${inspect}")"
  printf '%-16s state=%-8s health=%-8s restarts=%s\n' "${service}" "${status}" "${health}" "${restarts}"
  if [[ "${status}" != "running" || ( "${service}" == "cyberbro" && "${health}" != "healthy" ) ]]; then
    failed=1
  fi
done

printf '\n==> functional probes\n'
if curl -fsS --max-time 8 -o /dev/null "${CYBERBRO_URL}"; then
  printf 'OK: Cyberbro HTTP ready: %s\n' "${CYBERBRO_URL}"
else
  printf 'ERROR: Cyberbro HTTP probe failed: %s\n' "${CYBERBRO_URL}" >&2
  failed=1
fi
mcp_code="$(curl -sS --max-time 8 -o /dev/null -w '%{http_code}' "${MCP_URL}" || true)"
if [[ "${mcp_code}" == "000" || -z "${mcp_code}" ]]; then
  printf 'ERROR: Cyberbro MCP transport unreachable: %s\n' "${MCP_URL}" >&2
  failed=1
else
  printf 'OK: Cyberbro MCP transport reachable: http=%s\n' "${mcp_code}"
fi
[[ "${app_state}" == "RUNNING" ]] || failed=1

if ((failed > 0)) || [[ "${VERBOSE}" == "true" || "${VERBOSE}" == "1" ]]; then
  printf '\n==> recent TrueNAS app jobs\n'
  midclt call core.get_jobs |
    jq --arg app "${APP_ID}" '
      [
        .[]
        | select((.method // "") | startswith("app."))
        | select(((.arguments // []) | tostring) | contains($app))
        | {id,method,state,error}
      ]
      | sort_by(.id)
      | reverse
      | .[:5]
    ' || true
fi

if ((failed > 0)); then
  printf '\n==> bounded container logs\n'
  for service in cyberbro mcp-cyberbro; do
    container_id="${container_ids[${service}]:-}"
    [[ -n "${container_id}" ]] || continue
    printf '%s:\n' "${service}" >&2
    docker logs --tail 40 "${container_id}" 2>&1 | tail -40 || true
  done

  if command -v journalctl >/dev/null 2>&1; then
    printf '\n==> bounded Cyberbro Docker evidence\n'
    journalctl -u docker --since '-10 min' --no-pager 2>/dev/null |
      grep -Ei 'cyberbro|mcp-cyberbro|ix-cyberbro' |
      tail -40 || true
  fi

  fail "Cyberbro runtime diagnosis failed"
fi

if ((lifecycle_warning > 0)); then
  printf 'WARNING: Cyberbro is healthy now, but lifecycle errors were emitted above for operator review.\n' >&2
fi
printf 'OK: Cyberbro runtime diagnosis passed.\n'
