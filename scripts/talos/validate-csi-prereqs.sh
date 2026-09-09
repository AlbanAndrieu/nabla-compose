#!/usr/bin/env bash
set -euo pipefail

# Keep interactive diagnostics compact while preserving full CI/non-TTY output.
if [[ "${NABLA_DIAGNOSTIC_WRAPPED:-0}" != "1" && "${DIAGNOSTIC_FULL_OUTPUT:-0}" != "1" && ( -t 1 || "${DIAGNOSTIC_COMPACT_OUTPUT:-0}" == "1" ) ]]; then
  NABLA_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  NABLA_DIAGNOSTIC_WRAPPER="$(dirname -- "${NABLA_SCRIPT_DIR}")/run-diagnostic.sh"
  exec "${NABLA_DIAGNOSTIC_WRAPPER}"     "${NABLA_SCRIPT_DIR}/$(basename -- "${BASH_SOURCE[0]}")" "$@"
fi

ROOT="$(git rev-parse --show-toplevel)"
KUBECONFIG="${KUBECONFIG:-${ROOT}/.talos/generated/kubeconfig}"
TRUENAS_HOST="${TRUENAS_CSI_HOST:-172.17.0.24}"
EXPECTED_NODES="${K8S_EXPECTED_NODES:-3}"
EXPECTED_WORKERS="${K8S_EXPECTED_WORKERS:-2}"
STORAGE_CLASS="${K8S_CSI_STORAGE_CLASS:-nabla-truenas-nfs}"
CSI_ROOT="${ROOT}/kubernetes/truenas-csi"
DRIVER_MANIFEST="${CSI_ROOT}/nfs-driver.yaml"
STORAGE_CLASS_MANIFEST="${CSI_ROOT}/storageclass-nfs.yaml"
EXPECTED_CSI_VERSION="v1.0.3"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

ok() {
  printf '✅ %s\n' "$*"
}

for command in kubectl jq grep; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ -s "${KUBECONFIG}" ]] || fail "kubeconfig not found: ${KUBECONFIG}"
export KUBECONFIG

[[ "$(<"${CSI_ROOT}/VERSION")" == "${EXPECTED_CSI_VERSION}" ]] ||
  fail "TrueNAS CSI version pin must be ${EXPECTED_CSI_VERSION}"
[[ -s "${DRIVER_MANIFEST}" ]] || fail "missing ${DRIVER_MANIFEST}"
[[ -s "${STORAGE_CLASS_MANIFEST}" ]] || fail "missing ${STORAGE_CLASS_MANIFEST}"
grep -Fq "ghcr.io/truenas/truenas-csi:${EXPECTED_CSI_VERSION}" "${DRIVER_MANIFEST}" ||
  fail "CSI driver image is not pinned to ${EXPECTED_CSI_VERSION}"
if grep -Eq 'iscsiadm|/etc/iscsi|/var/lib/iscsi' "${DRIVER_MANIFEST}"; then
  fail "Talos first-storage manifest must remain NFS-only"
fi
ok "TrueNAS CSI ${EXPECTED_CSI_VERSION} NFS-only repository contract is pinned"

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

worker_count="$(
  jq '
    [
      .items[]
      | select(.metadata.labels["node-role.kubernetes.io/control-plane"] == null)
    ]
    | length
  ' <<<"${nodes_json}"
)"
[[ "${worker_count}" -ge "${EXPECTED_WORKERS}" ]] ||
  fail "expected at least ${EXPECTED_WORKERS} worker nodes, found ${worker_count}"
ok "${worker_count} worker nodes available for cross-node persistence smoke"

if timeout 3 bash -c "</dev/tcp/${TRUENAS_HOST}/2049" 2>/dev/null; then
  ok "TrueNAS NFS TCP/2049 reachable at ${TRUENAS_HOST}"
else
  fail "TrueNAS NFS TCP/2049 is not reachable at ${TRUENAS_HOST}"
fi

kubectl apply --dry-run=client -f "${DRIVER_MANIFEST}" >/dev/null
kubectl apply --dry-run=client -f "${STORAGE_CLASS_MANIFEST}" >/dev/null
ok "CSI driver and StorageClass manifests pass kubectl client validation"

if kubectl get storageclass "${STORAGE_CLASS}" >/dev/null 2>&1; then
  printf 'ℹ️  StorageClass %s already exists; inspect before applying repository state\n' "${STORAGE_CLASS}"
else
  printf 'ℹ️  StorageClass %s does not exist yet (expected before first install)\n' "${STORAGE_CLASS}"
fi

if kubectl get csidriver csi.truenas.io >/dev/null 2>&1; then
  printf 'ℹ️  CSIDriver csi.truenas.io is already registered; inspect ownership before applying\n'
else
  printf 'ℹ️  CSIDriver csi.truenas.io is not registered yet\n'
fi

if [[ -n "${TRUENAS_CSI_API_KEY:-}" ]]; then
  ok "TRUENAS_CSI_API_KEY is present in the environment (value not printed)"
else
  printf 'ℹ️  TRUENAS_CSI_API_KEY is not exported; read-only preflight does not require it\n'
fi

printf '⚠️  Upstream TrueNAS CSI %s still authenticates with deprecated auth.login_with_api_key. Validate it on TrueNAS 26 and track SCRAM/username support before TrueNAS 27.\n' "${EXPECTED_CSI_VERSION}"
printf '✅ CSI preflight complete: cluster, NFS reachability and pinned manifests are ready for the explicit install step\n'
