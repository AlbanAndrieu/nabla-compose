#!/usr/bin/env bash
# Read-only Akvorado orchestrator config mount attestation; never output YAML.
set -euo pipefail
[[ "$#" -le 1 && "${1:---check}" == --check ]] || {
  echo 'usage: bash scripts/truenas/diagnose-akvorado-config.sh --check' >&2
  exit 2
}
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
CONFIG="$ROOT/apps/akvorado/config/akvorado.yaml"
[[ -f "$CONFIG" && ! -L "$CONFIG" ]] || { echo 'BLOCKED: unsafe or missing Akvorado config'; exit 1; }
for cmd in docker sha256sum awk sort; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "BLOCKED: missing $cmd"; exit 2; }
done

# The TrueNAS App project can be ix-akvorado; never select fuzzy matches.
mapfile -t ids < <(
  for project in ix-akvorado akvorado; do
    docker ps -a --filter "label=com.docker.compose.project=$project" \
      --filter 'label=com.docker.compose.service=akvorado-orchestrator' \
      --format '{{.ID}}' 2>/dev/null || true
  done | awk 'length($0)>=12 && length($0)<=64 && $0 !~ /[^a-f0-9]/' | sort -u
)
if (("${#ids[@]}" != 1)); then
  printf 'BLOCKED: akvorado_orchestrator_container_matches=%d (expected exactly 1)\n' "${#ids[@]}"
  exit 1
fi
id="${ids[0]}"
state="$(docker inspect --type container --format '{{.State.Status}}' "$id" 2>/dev/null || true)"
if [[ "$state" != running ]]; then
  printf 'BLOCKED: akvorado_orchestrator_state=%s\n' "$state"
  exit 1
fi
host_hash="$(sha256sum "$CONFIG" | awk '{print $1}')"
runtime_digest="$(docker exec "$id" sha256sum /etc/akvorado/akvorado.yaml 2>/dev/null || true)"
runtime_hash="${runtime_digest%% *}"
[[ "$host_hash" =~ ^[a-f0-9]{64}$ ]] || { echo 'BLOCKED: host hash unavailable'; exit 1; }
if [[ ! "$runtime_hash" =~ ^[a-f0-9]{64}$ ]]; then
  echo 'BLOCKED: orchestrator config file unreadable in container'
  exit 1
fi
if [[ "$host_hash" != "$runtime_hash" ]]; then
  printf 'BLOCKED: orchestrator_config_bind=DRIFT (host/container SHA differ)\n'
  printf 'NEXT: compare stored TrueNAS Custom App configuration privately; do not restart automatically\n'
  exit 1
fi
printf 'OK: orchestrator_config_bind=MATCH (SHA256 equal)\n'
printf 'NOTE: bind equality does not attest in-memory config, metadata cache, exporter IP or fresh flows\n'
