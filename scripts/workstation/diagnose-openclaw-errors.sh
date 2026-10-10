#!/usr/bin/env bash
# Read-only aggregate of OpenClaw Gateway errors; never prints raw journal lines.
set -euo pipefail
usage() { echo "Usage: diagnose-openclaw-errors.sh [--since '2 hours ago' | --stdin]" >&2; }
mode=journal
since="2 hours ago"
case "${1:-}" in
  "") ;;
  --since) [[ $# -eq 2 ]] || { usage; exit 2; }; since="$2" ;;
  --stdin) [[ $# -eq 1 ]] || { usage; exit 2; }; mode=stdin ;;
  *) usage; exit 2 ;;
esac
aggregate() {
python3 -c '
import sys
from collections import Counter
counts = Counter()
for line in sys.stdin:
    s = line.lower()
    if "429" in s and ("budget has been exceeded" in s or "max budget" in s):
        counts["litellm_budget_429"] += 1
    if "401" in s and ("embeddings" in s or "invalid_api_key" in s):
        counts["embedding_auth_401"] += 1
    if "context-pressure-diagnostic" in s:
        counts["context_pressure"] += 1
    if "memory sync aborted" in s:
        counts["memory_sync_aborted"] += 1
    if "database integrity verification passed" in s:
        counts["sqlite_integrity_ok"] += 1
    if "connect econnrefused" in s:
        counts["gateway_connection_refused"] += 1
for key in ("litellm_budget_429", "embedding_auth_401", "context_pressure",
            "memory_sync_aborted", "sqlite_integrity_ok", "gateway_connection_refused"):
    print(f"{key}={counts[key]}")
if counts["litellm_budget_429"]:
    print("ACTION: inspect LiteLLM virtual-key budget; do not bypass cost limits")
if counts["embedding_auth_401"]:
    print("ACTION: fix embedding provider routing/secret expansion; preserve vector index")
if counts["context_pressure"]:
    print("ACTION: review session prompt size and compaction limits")
'
}
if [[ "${mode}" == stdin ]]; then
  aggregate
else
  journalctl --user -u openclaw-gateway.service --since "${since}" --no-pager -o cat |
    aggregate
fi
