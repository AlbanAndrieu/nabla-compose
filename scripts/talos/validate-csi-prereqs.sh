#!/usr/bin/env bash
set -euo pipefail

# Keep interactive diagnostics compact while preserving full CI/non-TTY output.
if [[ "${NABLA_DIAGNOSTIC_WRAPPED:-0}" != "1" &&
      "${DIAGNOSTIC_FULL_OUTPUT:-0}" != "1" &&
      ( -t 1 || "${DIAGNOSTIC_COMPACT_OUTPUT:-0}" == "1" ) ]]; then
  NABLA_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  NABLA_DIAGNOSTIC_WRAPPER="$(dirname -- "${NABLA_SCRIPT_DIR}")/run-diagnostic.sh"
  exec "${NABLA_DIAGNOSTIC_WRAPPER}" \
    "${NABLA_SCRIPT_DIR}/$(basename -- "${BASH_SOURCE[0]}")" "$@"
fi

ROOT="$(git rev-parse --show-toplevel)"
KUBECONFIG="${KUBECONFIG:-${ROOT}/.talos/generated/kubeconfig}"
TRUENAS_HOST="${TRUENAS_CSI_HOST:-172.17.0.24}"
EXPECTED_NODES="${K8S_EXPECTED_NODES:-3}"
STORAGE_CLASS="${K8S_CSI_STORAGE_CLASS:-nabla-truenas-nfs}"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

ok() {
  printf '✅ %s\n' "$*"
}

for command in kubectl jq; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ -s "${KUBECONFIG}" ]] || fail "kubeconfig not found: ${KUBECONFIG}"
export KUBECONFIG

nodes_json="$(kubectl get nodes -o json)"
node_count="$(jq '.items | length' <<<"${nodes_json}")"
[[ "${node_count}" -eq "${EXPECTED_NODES}" ]] ||
  fail "expected ${EXPECTED_NODES} Kubernetes nodes, found ${node_count}"

not_ready="$(
  jq -r '
    .items[]
    | select(
        ([.status.conditions[]? | select(.type == "Ready" and .status == "True")] | length) == 0
      )
    | .metadata.name
  ' <<<"${nodes_json}"
)"
[[ -z "${not_ready}" ]] || fail "nodes not Ready: ${not_ready//$'\n'/, }"
ok "all ${node_count} Kubernetes nodes are Ready"

if timeout 3 bash -c "</dev/tcp/${TRUENAS_HOST}/2049" 2>/dev/null; then
  ok "TrueNAS NFS TCP/2049 reachable at ${TRUENAS_HOST}"
else
  fail "TrueNAS NFS TCP/2049 is not reachable at ${TRUENAS_HOST}"
fi

if kubectl get storageclass "${STORAGE_CLASS}" >/dev/null 2>&1; then
  printf 'ℹ️  StorageClass %s already exists; review before installing or changing CSI\n' "${STORAGE_CLASS}"
else
  printf 'ℹ️  StorageClass %s does not exist yet (expected before first CSI install)\n' "${STORAGE_CLASS}"
fi

csi_drivers="$(kubectl get csidriver -o json 2>/dev/null || printf '{"items":[]}')"
driver_names="$(jq -r '.items[].metadata.name' <<<"${csi_drivers}")"
if [[ -n "${driver_names}" ]]; then
  printf 'ℹ️  Existing CSI drivers:\n%s\n' "${driver_names}"
else
  printf 'ℹ️  No CSIDriver objects are currently registered\n'
fi

if [[ -n "${TRUENAS_CSI_API_KEY:-}" ]]; then
  printf '✅ TRUENAS_CSI_API_KEY is present in the environment (value not printed)\n'
else
  printf 'ℹ️  TRUENAS_CSI_API_KEY is not exported; this read-only preflight does not require it\n'
fi

printf '✅ CSI preflight complete: cluster readiness and NFS reachability are suitable for the next reviewed install step\n'
