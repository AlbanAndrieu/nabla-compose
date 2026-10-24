#!/usr/bin/env bash
# OpenRAG 0.7.1 multi-container dependency triage. Read-only, redacted.
set -euo pipefail

case "${1:---check}" in
  --check) ;;
  *) printf 'usage: bash %s --check\n' "$0" >&2; exit 2 ;;
esac
(( $# <= 1 )) || { printf 'unexpected arguments\n' >&2; exit 2; }

# Never inspect .Config.Env / secrets, never print Docker health log outputs.
# Names are allowlisted in code; caller cannot inject Docker container names.
command -v docker >/dev/null 2>&1 || { printf 'ERROR docker missing\n' >&2; exit 2; }
# TrueNAS may create ix-<app>-<service>-1 instead of a literal
# container_name, especially when its stored Custom App Compose is stale.
# Resolve only Docker Compose labels for the expected App+service pair;
# never pick an arbitrary similarly named container or leak its metadata.
resolve_container() {
  local app="$1" service="$2" candidate id
  if docker inspect --type container "$service" >/dev/null 2>&1; then
    printf '%s' "$service"
    return 0
  fi
  local -a found=()
  for project in "ix-${app}" "$app"; do
    while IFS= read -r id; do
      [[ "$id" =~ ^[a-f0-9]{12,64}$ ]] || continue
      if [[ ! " ${found[*]} " == *" $id "* ]]; then
        found+=("$id")
      fi
    done < <(docker ps -a \
      --filter "label=com.docker.compose.project=${project}" \
      --filter "label=com.docker.compose.service=${service}" \
      --format '{{.ID}}' 2>/dev/null || true)
  done
  if ((${#found[@]} == 1)); then
    printf '%s' "${found[0]}"
    return 0
  fi
  return 1
}

get_state() {
  local app="$1" service="$2" resolved raw status health exit_code restarts
  if ! resolved="$(resolve_container "$app" "$service")"; then
    printf 'missing none - -\n'
    return 0
  fi
  if ! raw="$(docker inspect --type container --format \
    '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} {{.State.ExitCode}} {{.RestartCount}}' \
    "$resolved" 2>/dev/null)"; then
    printf 'missing none - -\n'
    return 0
  fi
  read -r status health exit_code restarts <<< "$raw"
  case "$status" in running|created|restarting|exited|dead|paused) ;; *) status=unknown ;; esac
  case "$health" in healthy|unhealthy|starting|none) ;; *) health=unknown ;; esac
  [[ "$exit_code" =~ ^[0-9]+$ ]] || exit_code='-'
  [[ "$restarts" =~ ^[0-9]+$ ]] || restarts='-'
  printf '%s %s %s %s\n' "$status" "$health" "$exit_code" "$restarts"
}

backend="$(get_state openrag openrag-backend)"
frontend="$(get_state openrag openrag-frontend)"
langflow="$(get_state langflow langflow)"
opensearch="$(get_state opensearch opensearch)"
docling="$(get_state docling docling)"

# Safe TrueNAS middleware signal to distinguish DEPLOYING App from an
# absent/misnamed Docker project; never print app.query configuration.
if [[ "${NABLA_DIAGNOSTIC_OFFLINE:-0}" != 1 ]] && command -v midclt >/dev/null 2>&1 && command -v jq >/dev/null 2>&1; then
  if command -v timeout >/dev/null 2>&1; then
    states="$(timeout 15 midclt call app.query 2>/dev/null | jq -er \
      '[.[] | select(.id == "openrag" or .id == "opensearch") |
       (.id + "=" + (.state // "UNKNOWN"))] | sort | join(" ")' 2>/dev/null)" || states=""
    if [[ -n "$states" ]]; then
      printf 'TrueNAS Apps: %s\n' "$states"
    else
      printf 'TrueNAS Apps: unavailable_or_not_listed\n'
    fi
  fi
fi
printf 'OpenRAG dependency state (metadata only, no secrets)\n'
for name in openrag-backend openrag-frontend langflow opensearch docling; do
  case "$name" in
    openrag-backend) row="$backend" ;;
    openrag-frontend) row="$frontend" ;;
    langflow) row="$langflow" ;;
    opensearch) row="$opensearch" ;;
    docling) row="$docling" ;;
  esac
  read -r state health exit_code restarts <<< "$row"
  printf '%s status=%s health=%s exit=%s restarts=%s\n' \
    "$name" "$state" "$health" "$exit_code" "$restarts"
done

read -r backend_state backend_health _ <<< "$backend"
read -r frontend_state frontend_health _ <<< "$frontend"
read -r langflow_state langflow_health _ <<< "$langflow"
read -r search_state search_health _ <<< "$opensearch"

# The declared Compose has depends_on backend: service_healthy. A backend
# merely running, without a healthy Docker healthcheck, cannot start frontend.
if [[ "$backend_state" != running || "$backend_health" != healthy ]]; then
  printf 'BLOCKED: backend not running+healthy, frontend dependency unsatisfied\n' >&2
  printf 'NEXT: check backend health and OpenSearch/Langflow dependencies before any reviewed reconciliation\n' >&2
  exit 1
fi
if [[ "$frontend_state" == created ]]; then
  if [[ "$langflow_state" != running || "$search_state" != running ]]; then
    printf 'BLOCKED: frontend created; shared Langflow/OpenSearch prerequisite not running\n' >&2
  else
    printf 'BLOCKED: frontend created despite healthy backend; inspect TrueNAS stored Compose lifecycle/dependencies\n' >&2
    printf 'NEXT: compare current TrueNAS Custom App definition to apps/openrag/compose.yml before a SINGLE reviewed reconcile\n' >&2
  fi
  exit 1
fi
if [[ "$frontend_state" != running || "$frontend_health" != healthy ]]; then
  printf 'BLOCKED: frontend is not running+healthy; inspect bounded health categories privately\n' >&2
  exit 1
fi
if [[ "$langflow_state" != running || "$search_state" != running ]]; then
  printf 'BLOCKED: Langflow or OpenSearch not running; do not reindex\n' >&2
  exit 1
fi
if [[ "$langflow_health" == unhealthy || "$search_health" == unhealthy ]]; then
  printf 'WARN: shared dependency unhealthy; verify functional endpoints before accepting OpenRAG\n' >&2
  exit 1
fi
printf 'OK: OpenRAG backend/frontend running+healthy; shared dependencies running\n'
printf 'INFO: Docling health, embedding, ingestion and corpus coverage require separate smoke checks\n'
