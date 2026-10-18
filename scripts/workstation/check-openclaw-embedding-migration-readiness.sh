#!/usr/bin/env bash
# Read-only batch acceptance for the OpenClaw → LiteLLM embedding migration.
set -u
set -o pipefail
export PYTHONDONTWRITEBYTECODE=1
export NO_COLOR=1
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 2
umask 077
if [[ -n "${LITELLM_MASTER_KEY:-}" ]]; then
  printf '%s\n' 'ERROR: unset LITELLM_MASTER_KEY before running read-only acceptance (never log admin credentials)' >&2
  exit 2
fi
fail=0
run() {
  local name="$1"; shift
  printf '\n== %s ==\n' "$name"
  "$@"
  local rc=$?
  printf 'check=%s exit_code=%d\n' "$name" "$rc"
  if (( rc != 0 )); then fail=1; fi
}
run offline_contracts python3 -m unittest discover -s tests -p 'test_openclaw_embeddings_key_storage_security.py' -v
run secret_audit_contracts python3 -m unittest discover -s tests -p 'test_openclaw_memory_secret_audit.py' -v
run key_provisioning_preflight python3 scripts/workstation/provision-openclaw-embeddings-litellm-key.py --check
run openclaw_schema_and_file_preflight python3 scripts/workstation/check-openclaw-litellm-memory-config.py --check
run strict_openclaw_secrets_audit python3 scripts/workstation/check-openclaw-litellm-memory-config.py --audit
run memory_migration_preflight python3 scripts/workstation/prepare-openclaw-embedding-migration.py --check
run memory_snapshot_verification python3 scripts/workstation/prepare-openclaw-embedding-migration.py --verify-backup
# Never automatically call --apply, the embedding API, or reindex.
printf '\nacceptance=%s migration_applied=false key_created=false embeddings_requested=false\n' "$([[ "$fail" == 0 ]] && echo ready_for_review || echo blocked)"
exit "$fail"
