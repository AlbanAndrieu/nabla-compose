#!/usr/bin/env bash
# Read-only, metadata-only OpenRAG startup readiness. Does NOT start Apps.
set -euo pipefail

[[ "$#" -le 1 && "${1:---check}" == --check ]] || {
  echo 'usage: bash scripts/truenas/diagnose-openrag-startup.sh --check' >&2
  exit 2
}
blocked=0
fail_gate() {
  printf 'BLOCKED: %s\n' "$1"
  blocked=$((blocked + 1))
}
# TrueNAS middleware CLI is only installed on the appliance. Do not
# assume that a workstation with this Git checkout is a TrueNAS runtime.
if ! command -v midclt >/dev/null 2>&1; then
  printf 'host_context=NOT_TRUENAS_OR_MIDCLT_NOT_IN_PATH\n' >&2
  printf 'OPENRAG_STARTUP_PREFLIGHT=NOT_RUN\n' >&2
  printf 'NEXT: run from a TrueNAS shell with midclt; do not install appliance tools on the workstation\n' >&2
  exit 2
fi
for tool in timeout jq zfs stat grep curl readlink; do
  command -v "${tool}" >/dev/null 2>&1 || {
    echo "BLOCKED: missing diagnostic binary: ${tool}" >&2
    exit 2
  }
done

# Filter middleware JSON IN MEMORY. Never print raw app.query, custom config or env.
app_state="$(timeout 15 midclt call app.query 2>/dev/null |
  jq -er '[.[] | select(.id == "openrag") | (.state // "UNKNOWN")] |
    if length == 1 then .[0] else empty end' 2>/dev/null)" || app_state=UNKNOWN
case "${app_state}" in
  STOPPED) echo 'openrag_app=STOPPED start_authorization=REQUIRED'; fail_gate 'TrueNAS App is STOPPED; operator must explicitly approve start after preflight' ;;
  RUNNING) echo 'openrag_app=RUNNING';;
  DEPLOYING|CRASHED|STOPPING) echo "openrag_app=${app_state}"; fail_gate 'TrueNAS App lifecycle has not converged' ;;
  *) echo 'openrag_app=UNKNOWN'; fail_gate 'cannot confirm TrueNAS App lifecycle' ;;
esac

# When the App is RUNNING, inspect both declared Compose components. Docker
# healthchecks cover the backend /health and frontend /health/collective_health.
# Metadata only: never print Docker environment, healthcheck output or logs.
# For a STOPPED App, component absence does not change the start authorization.
if [[ "${app_state}" == RUNNING ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    fail_gate 'Docker unavailable on TrueNAS; backend/frontend health unknown'
  else
    for service in openrag-backend openrag-frontend; do
      health_record="$(timeout 10 docker inspect --type container --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${service}" 2>/dev/null)" || health_record='unknown|unknown'
      IFS='|' read -r container_state container_health <<<"${health_record}"
      case "${container_state}" in running|exited|restarting|created|dead) ;; *) container_state=unknown ;; esac
      case "${container_health}" in healthy|unhealthy|starting|none) ;; *) container_health=unknown ;; esac
      printf 'openrag_component=%s state=%s health=%s\n' "${service}" "${container_state}" "${container_health}"
      if [[ "${container_state}" != running || "${container_health}" != healthy ]]; then
        fail_gate 'OpenRAG backend/frontend container not running+healthy'
      fi
    done
  fi
fi

# Required secrets must exist as root-owned 0600 or 0400 files.
# Only emit required KEY names and status, never content or line values.
secret="${OPENRAG_SECRET_FILE:-/mnt/cpool/secrets/runtime/openrag/.env.secrets}"
# The reviewed migrations may finalize the legacy path as a compatibility
# symlink. Accept ONLY its exact canonical destination; reject other links.
if [[ -L "${secret}" ]]; then
  resolved="$(readlink -f -- "${secret}" 2>/dev/null || true)"
  if [[ "${secret}" == /mnt/cpool/openrag/.env.secrets &&
        "${resolved}" == /mnt/cpool/secrets/runtime/openrag/.env.secrets ]]; then
    echo 'secret_path=accepted_canonical_compatibility_symlink'
    secret="${resolved}"
  else
    fail_gate 'OpenRAG secret symlink is not the reviewed canonical migration target'
    secret=''
  fi
fi
if [[ ! -f "${secret}" || ! -r "${secret}" ]]; then
  fail_gate 'OpenRAG secret file missing or unreadable (run with sudo)'
else
  mode="$(stat -c '%a' -- "${secret}" 2>/dev/null || true)"
  owner="$(stat -c '%u' -- "${secret}" 2>/dev/null || true)"
  if [[ "${mode}" != 600 && "${mode}" != 400 ]]; then
    fail_gate 'OpenRAG secret file mode is not private 0600/0400'
  else
    echo 'secret_file_mode=private'
  fi
  if [[ "${secret}" == /mnt/cpool/* && "${owner}" != 0 ]]; then
    fail_gate 'TrueNAS OpenRAG secret file is not root owned'
  fi
  for name in OPENSEARCH_PASSWORD LANGFLOW_KEY LITELLM_IDE_API_KEY OPENRAG_ENCRYPTION_KEY; do
    if grep -Eq "^${name}=.+" -- "${secret}"; then
      printf 'secret_%s=present\n' "${name}"
    else
      printf 'secret_%s=missing\n' "${name}"
      blocked=$((blocked + 1))
    fi
  done
fi

# Scope to the one approved dataset, never walk its file tree.
dataset="${OPENRAG_ZFS_DATASET:-cpool/bababou}"
source="${OPENRAG_BABABOU_SOURCE:-/mnt/cpool/bababou}"
if [[ "${source}" != /* || -L "${source}" ||
      ( "${dataset}" == cpool/bababou && "${source}" != /mnt/cpool/* ) ]]; then
  fail_gate 'corpus mountpoint is non-absolute, symlinked or outside the expected cpool prefix'
else
  metadata="$(zfs list -H -o mountpoint,mounted "${dataset}" 2>/dev/null)" || metadata=''
  IFS=$'\t' read -r actual mounted <<<"${metadata}"
  if [[ "${mounted}" != yes || "${actual}" != "${source}" || ! -d "${source}" ]]; then
    fail_gate 'ZFS source absent, not mounted or differs from configured corpus path'
  else
    echo 'corpus_zfs_mount=verified corpus_data=not_read'
  fi
fi

# No key or model request. The anonymous /v1/models probe generated
# avoidable authentication failures on Workstation LiteLLM in the past.
# Use only the advertised anonymous liveliness route. Authenticated model
# inventory and inference remain separate, opt-in functional checks.
http_code() {
  curl --silent --show-error --output /dev/null --max-time 6 \
    --write-out '%{http_code}' "$1" 2>/dev/null || true
}
langflow_status="$(http_code 'http://172.17.0.24:7860/health_check')"
if [[ "${langflow_status}" == 200 ]]; then
  echo 'langflow_readiness=HTTP_200'
else
  fail_gate 'global Langflow /health_check is not HTTP 200'
fi
litellm_status="$(http_code 'http://172.17.0.57:4000/health/liveliness')"
case "${litellm_status}" in
  200) echo 'litellm_liveliness=HTTP_200 models_auth=not_tested' ;;
  *) echo 'WARN: litellm_liveliness=unverified; authenticated chat/embedding acceptance pending' ;;
esac
docling_status="$(http_code 'http://172.17.0.24:5001/ready')"
if [[ "${docling_status}" == 200 ]]; then
  echo 'docling_ingestion_prerequisite=HTTP_200'
else
  echo 'WARN: docling_ingestion_prerequisite=unavailable; do not ingest documents'
fi

if (( blocked > 0 )); then
  printf 'OPENRAG_STARTUP_PREFLIGHT=BLOCKED gates=%d\n' "${blocked}"
  printf 'NEXT: do not start/redeploy or index; review TrueNAS app lifecycle, secrets, dataset and shared auth\n'
  exit 1
fi
echo 'OPENRAG_STARTUP_PREFLIGHT=READY_FOR_OPERATOR_REVIEW'
echo 'NOTE: running+healthy backend/frontend, Langflow auth, OpenSearch auth and LiteLLM embedding still require live verification'
