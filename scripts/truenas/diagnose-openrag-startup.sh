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
for tool in midclt timeout jq zfs stat grep curl; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "BLOCKED: missing diagnostic binary: $tool" >&2
    exit 2
  }
done

# Filter middleware JSON IN MEMORY. Never print raw app.query, custom config or env.
app_state="$(timeout 15 midclt call app.query 2>/dev/null |
  jq -er '[.[] | select(.id == "openrag") | (.state // "UNKNOWN")] |
    if length == 1 then .[0] else empty end' 2>/dev/null)" || app_state=UNKNOWN
case "$app_state" in
  STOPPED) echo 'openrag_app=STOPPED start_authorization=REQUIRED'; fail_gate 'TrueNAS App is STOPPED; operator must explicitly approve start after preflight' ;;
  RUNNING) echo 'openrag_app=RUNNING';;
  DEPLOYING|CRASHED|STOPPING) echo "openrag_app=$app_state"; fail_gate 'TrueNAS App lifecycle has not converged' ;;
  *) echo 'openrag_app=UNKNOWN'; fail_gate 'cannot confirm TrueNAS App lifecycle' ;;
esac

# Required secrets must exist as root-owned 0600 or 0400 files.
# Only emit required KEY names and status, never content or line values.
secret="${OPENRAG_SECRET_FILE:-/mnt/cpool/openrag/.env.secrets}"
if [[ ! -f "$secret" || -L "$secret" || ! -r "$secret" ]]; then
  fail_gate 'OpenRAG secret file missing, symlinked or unreadable (run with sudo)'
else
  mode="$(stat -c '%a' -- "$secret" 2>/dev/null || true)"
  owner="$(stat -c '%u' -- "$secret" 2>/dev/null || true)"
  if [[ "$mode" != 600 && "$mode" != 400 ]]; then
    fail_gate 'OpenRAG secret file mode is not private 0600/0400'
  else
    echo 'secret_file_mode=private'
  fi
  if [[ "$secret" == /mnt/cpool/* && "$owner" != 0 ]]; then
    fail_gate 'TrueNAS OpenRAG secret file is not root owned'
  fi
  for name in OPENSEARCH_PASSWORD LANGFLOW_KEY LITELLM_IDE_API_KEY OPENRAG_ENCRYPTION_KEY; do
    if grep -Eq "^${name}=.+" -- "$secret"; then
      printf 'secret_%s=present\n' "$name"
    else
      printf 'secret_%s=missing\n' "$name"
      blocked=$((blocked + 1))
    fi
  done
fi

# Scope to the one approved dataset, never walk its file tree.
dataset="${OPENRAG_ZFS_DATASET:-cpool/bababou}"
source="${OPENRAG_BABABOU_SOURCE:-/mnt/cpool/bababou}"
if [[ "$source" != /* || -L "$source" ||
      ( "$dataset" == cpool/bababou && "$source" != /mnt/cpool/* ) ]]; then
  fail_gate 'corpus mountpoint is non-absolute, symlinked or outside the expected cpool prefix'
else
  metadata="$(zfs list -H -o mountpoint,mounted "$dataset" 2>/dev/null)" || metadata=''
  IFS=$'\t' read -r actual mounted <<<"$metadata"
  if [[ "$mounted" != yes || "$actual" != "$source" || ! -d "$source" ]]; then
    fail_gate 'ZFS source absent, not mounted or differs from configured corpus path'
  else
    echo 'corpus_zfs_mount=verified corpus_data=not_read'
  fi
fi

# Authentication and functionality MUST be proven separately. No API key used
# here: GET /v1/models can return 401 while the transport is reachable.
http_code() {
  curl --silent --show-error --output /dev/null --max-time 6 \
    --write-out '%{http_code}' "$1" 2>/dev/null || true
}
langflow_status="$(http_code 'http://172.17.0.24:7860/health_check')"
if [[ "$langflow_status" == 200 ]]; then
  echo 'langflow_readiness=HTTP_200'
else
  fail_gate 'global Langflow /health_check is not HTTP 200'
fi
litellm_status="$(http_code 'http://172.17.0.57:4000/v1/models')"
case "$litellm_status" in
  200) echo 'litellm_transport=reachable models_auth=not_verified' ;;
  401|403) echo 'litellm_transport=reachable models_auth=required_not_verified' ;;
  *) echo 'WARN: litellm_transport=unverified; chat/embedding acceptance pending' ;;
esac
docling_status="$(http_code 'http://172.17.0.24:5001/ready')"
if [[ "$docling_status" == 200 ]]; then
  echo 'docling_ingestion_prerequisite=HTTP_200'
else
  echo 'WARN: docling_ingestion_prerequisite=unavailable; do not ingest documents'
fi

if (( blocked > 0 )); then
  printf 'OPENRAG_STARTUP_PREFLIGHT=BLOCKED gates=%d\n' "$blocked"
  printf 'NEXT: do not start/redeploy or index; review TrueNAS app lifecycle, secrets, dataset and shared auth\n'
  exit 1
fi
echo 'OPENRAG_STARTUP_PREFLIGHT=READY_FOR_OPERATOR_REVIEW'
echo 'NOTE: running+healthy backend/frontend, Langflow auth, OpenSearch auth and LiteLLM embedding still require live verification'
