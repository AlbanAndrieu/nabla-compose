#!/usr/bin/env bash
set -euo pipefail

# Keep interactive diagnostics compact while preserving full CI/non-TTY output.
if [[ "${NABLA_DIAGNOSTIC_WRAPPED:-0}" != "1" && "${DIAGNOSTIC_FULL_OUTPUT:-0}" != "1" && ( -t 1 || "${DIAGNOSTIC_COMPACT_OUTPUT:-0}" == "1" ) ]]; then
  NABLA_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  NABLA_DIAGNOSTIC_WRAPPER="$(dirname -- "${NABLA_SCRIPT_DIR}")/run-diagnostic.sh"
  exec "${NABLA_DIAGNOSTIC_WRAPPER}" \
    "${NABLA_SCRIPT_DIR}/$(basename -- "${BASH_SOURCE[0]}")" "$@"
fi

ROOT="$(git rev-parse --show-toplevel)"
# shellcheck source=scripts/talos/lib/client-config.sh
source "${ROOT}/scripts/talos/lib/client-config.sh"
nabla_resolve_talos_client_config "${ROOT}"
TRUENAS_HOST="${TRUENAS_CSI_HOST:-172.17.0.24}"
TRUENAS_CSI_DATASET="${TRUENAS_CSI_DATASET:-cpool/k8s/csi}"
TRUENAS_CSI_MOUNTPOINT="${TRUENAS_CSI_MOUNTPOINT:-/mnt/cpool/k8s/csi}"
EXPECTED_NODES="${K8S_EXPECTED_NODES:-3}"
EXPECTED_WORKERS="${K8S_EXPECTED_WORKERS:-2}"
STORAGE_CLASS="${K8S_CSI_STORAGE_CLASS:-nabla-truenas-nfs}"
CSI_ROOT="${ROOT}/kubernetes/truenas-csi"
DRIVER_MANIFEST="${CSI_ROOT}/nfs-driver.yaml"
STORAGE_CLASS_MANIFEST="${CSI_ROOT}/storageclass-nfs.yaml"
EXPECTED_CSI_VERSION="v1.0.3"
CONTROLLER_CLUSTERROLE="truenas-csi-controller-role"
CONTROLLER_SERVICE_ACCOUNT="system:serviceaccount:truenas-csi:truenas-csi-controller-sa"
VOLUME_ATTACHMENT_RESOURCE="volumeattachments.storage.k8s.io"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

ok() {
  printf '✅ %s\n' "$*"
}

controller_runtime_converged() {
  local deployment_json desired updated ready available unavailable generation observed progress_deadline
  local converged=true

  if ! kubectl -n truenas-csi get deployment truenas-csi-controller >/dev/null 2>&1; then
    return 0
  fi

  deployment_json="$(kubectl -n truenas-csi get deployment truenas-csi-controller -o json)"
  desired="$(jq -r '.spec.replicas // 1' <<<"${deployment_json}")"
  updated="$(jq -r '.status.updatedReplicas // 0' <<<"${deployment_json}")"
  ready="$(jq -r '.status.readyReplicas // 0' <<<"${deployment_json}")"
  available="$(jq -r '.status.availableReplicas // 0' <<<"${deployment_json}")"
  unavailable="$(jq -r '.status.unavailableReplicas // 0' <<<"${deployment_json}")"
  generation="$(jq -r '.metadata.generation // 0' <<<"${deployment_json}")"
  observed="$(jq -r '.status.observedGeneration // 0' <<<"${deployment_json}")"
  progress_deadline="$(jq -r '[.status.conditions[]? | select(.type == "Progressing" and .status == "False" and .reason == "ProgressDeadlineExceeded")] | length' <<<"${deployment_json}")"

  [[ "${observed}" -ge "${generation}" ]] || converged=false
  [[ "${updated}" -eq "${desired}" ]] || converged=false
  [[ "${ready}" -eq "${desired}" ]] || converged=false
  [[ "${available}" -eq "${desired}" ]] || converged=false
  [[ "${unavailable}" -eq 0 ]] || converged=false
  [[ "${progress_deadline}" -eq 0 ]] || converged=false

  if [[ "${converged}" == "true" ]]; then
    ok "TrueNAS CSI controller runtime is fully converged"
    return 0
  fi

  printf '❌ TrueNAS CSI controller runtime is not converged: desired=%s updated=%s ready=%s available=%s unavailable=%s generation=%s observed=%s progressDeadlineExceeded=%s\n' \
    "${desired}" "${updated}" "${ready}" "${available}" "${unavailable}" "${generation}" "${observed}" "${progress_deadline}" >&2
  kubectl -n truenas-csi get deployment,rs,pod -l app=truenas-csi-controller -o wide >&2 2>/dev/null || true
  return 1
}

for command in kubectl jq grep timeout; do
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
grep -Fq "registry.k8s.io/sig-storage/csi-attacher:v4.11.0" "${DRIVER_MANIFEST}" ||
  fail "CSI controller manifest is missing csi-attacher:v4.11.0"
grep -Fq "attachRequired: true" "${DRIVER_MANIFEST}" ||
  fail "CSIDriver manifest must enable attachRequired so ControllerPublishVolume supplies publishContext"
if grep -Eq 'iscsiadm|/etc/iscsi|/var/lib/iscsi' "${DRIVER_MANIFEST}"; then
  fail "Talos first-storage manifest must remain NFS-only"
fi
ok "TrueNAS CSI ${EXPECTED_CSI_VERSION} NFS-only repository contract is pinned with controller publish enabled"

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

# /mnt/cpool/... belongs to the TrueNAS appliance. Do not interpret its absence
# on a workstation as storage failure. Verify the mountpoint only when the
# current execution environment has the TrueNAS middleware client.
if command -v midclt >/dev/null 2>&1; then
  [[ -d "${TRUENAS_CSI_MOUNTPOINT}" ]] ||
    fail "TrueNAS CSI parent mountpoint is missing on the appliance: ${TRUENAS_CSI_MOUNTPOINT}"
  ok "TrueNAS CSI parent mountpoint exists on the appliance: ${TRUENAS_CSI_MOUNTPOINT}"

  dataset_json="$(midclt call pool.dataset.query "[[\"id\",\"=\",\"${TRUENAS_CSI_DATASET}\"]]" 2>/dev/null)" ||
    fail "TrueNAS dataset API query failed for ${TRUENAS_CSI_DATASET}"
  dataset_count="$(jq 'length' <<<"${dataset_json}")"
  [[ "${dataset_count}" -eq 1 ]] ||
    fail "TrueNAS CSI parent dataset not found: ${TRUENAS_CSI_DATASET}"
  dataset_mountpoint="$(jq -r '.[0].mountpoint // empty' <<<"${dataset_json}")"
  [[ "${dataset_mountpoint}" == "${TRUENAS_CSI_MOUNTPOINT}" ]] ||
    fail "TrueNAS CSI parent dataset mountpoint mismatch: ${dataset_mountpoint:-missing}"
  ok "TrueNAS CSI parent dataset verified: ${TRUENAS_CSI_DATASET}"
else
  printf 'ℹ️  TrueNAS dataset/mountpoint verification skipped on this non-appliance operator; TCP/2049 reachability remains the workstation-side storage prerequisite\n'
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
  attach_required="$(kubectl get csidriver csi.truenas.io -o jsonpath='{.spec.attachRequired}')"
  [[ "${attach_required}" == "true" ]] ||
    fail "installed CSIDriver attachRequired=${attach_required:-missing}; this immutable drift skips ControllerPublishVolume and leaves publishContext empty"
  ok "installed CSIDriver csi.truenas.io enables ControllerPublishVolume"
else
  printf 'ℹ️  CSIDriver csi.truenas.io is not registered yet\n'
fi

if kubectl -n truenas-csi get deployment truenas-csi-controller >/dev/null 2>&1; then
  controller_containers="$(kubectl -n truenas-csi get deployment truenas-csi-controller -o jsonpath='{.spec.template.spec.containers[*].name}')"
  [[ " ${controller_containers} " == *" csi-attacher "* ]] ||
    fail "installed CSI controller has no csi-attacher; ControllerPublishVolume cannot populate VolumeAttachment attachmentMetadata"
  ok "installed CSI controller includes csi-attacher"
  controller_runtime_converged ||
    fail "installed CSI controller is not runtime-converged; authentication/socket/rollout must be healthy before storage acceptance"
fi

if kubectl get clusterrole "${CONTROLLER_CLUSTERROLE}" >/dev/null 2>&1; then
  for verb in get list watch patch; do
    if [[ "$(kubectl auth can-i \
      --as="${CONTROLLER_SERVICE_ACCOUNT}" \
      "${verb}" "${VOLUME_ATTACHMENT_RESOURCE}" 2>/dev/null)" != "yes" ]]; then
      fail "installed CSI controller cannot ${verb} ${VOLUME_ATTACHMENT_RESOURCE}; csi-attacher cannot complete the controller publish path"
    fi
  done
  if [[ "$(kubectl auth can-i \
    --as="${CONTROLLER_SERVICE_ACCOUNT}" \
    patch "${VOLUME_ATTACHMENT_RESOURCE}" --subresource=status 2>/dev/null)" != "yes" ]]; then
    fail "installed CSI controller cannot patch ${VOLUME_ATTACHMENT_RESOURCE}/status; publishContext cannot be persisted as attachmentMetadata"
  fi
  ok "installed CSI controller can read/patch VolumeAttachment and patch status"
else
  printf 'ℹ️  CSI controller ClusterRole is not installed yet; install helper will create the publishContext RBAC contract\n'
fi

if [[ -n "${TRUENAS_CSI_API_KEY:-}" ]]; then
  ok "TRUENAS_CSI_API_KEY is present in the environment (value not printed)"
else
  printf 'ℹ️  TRUENAS_CSI_API_KEY is not exported; read-only preflight does not require it\n'
fi

printf '⚠️  Upstream TrueNAS CSI %s still authenticates with deprecated auth.login_with_api_key. Validate it on TrueNAS 26 and track SCRAM/username support before TrueNAS 27.\n' "${EXPECTED_CSI_VERSION}"
printf '✅ CSI preflight complete: cluster, NFS reachability, controller runtime, publish path, RBAC and pinned manifests are ready for the explicit storage smoke\n'
