#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
KUBECONFIG="${KUBECONFIG:-${ROOT}/.talos/generated/kubeconfig}"
WORKER_A_IP="${TALOS_WORKER_A_IP:-172.17.0.51}"
WORKER_B_IP="${TALOS_WORKER_B_IP:-172.17.0.52}"
NAMESPACE="${K8S_STORAGE_SMOKE_NAMESPACE:-nabla-storage-smoke-$$}"
STORAGE_CLASS="${K8S_STORAGE_SMOKE_CLASS:-truenas-nfs-smoke}"
IMAGE="${K8S_STORAGE_SMOKE_IMAGE:-busybox:1.37.0}"
PVC_NAME="persistence-probe"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [[ "${namespace_created:-false}" == "true" ]]; then
    kubectl delete namespace "${NAMESPACE}" --wait=false >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

for command in kubectl jq; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ -s "${KUBECONFIG}" ]] || fail "Kubeconfig not found: ${KUBECONFIG}"
export KUBECONFIG
kubectl get storageclass "${STORAGE_CLASS}" >/dev/null ||
  fail "StorageClass not found: ${STORAGE_CLASS}"

nodes_json="$(kubectl get nodes -o json)"
node_for_ip() {
  local node_ip="$1"

  jq -r --arg ip "${node_ip}" '
    .items[]
    | select(any(.status.addresses[]?; .type == "InternalIP" and .address == $ip))
    | .metadata.name
  ' <<<"${nodes_json}"
}

worker_a_node="$(node_for_ip "${WORKER_A_IP}")"
worker_b_node="$(node_for_ip "${WORKER_B_IP}")"
[[ -n "${worker_a_node}" ]] || fail "cannot resolve Kubernetes node for ${WORKER_A_IP}"
[[ -n "${worker_b_node}" ]] || fail "cannot resolve Kubernetes node for ${WORKER_B_IP}"
[[ "${worker_a_node}" != "${worker_b_node}" ]] ||
  fail "worker IPs resolve to the same Kubernetes node: ${worker_a_node}"

printf '🔎 creating restricted storage smoke namespace %s\n' "${NAMESPACE}"
kubectl create namespace "${NAMESPACE}" >/dev/null
namespace_created=true
kubectl label namespace "${NAMESPACE}" \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/warn=restricted \
  --overwrite >/dev/null

cat <<EOF_MANIFEST | kubectl apply -f - >/dev/null
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ${PVC_NAME}
  namespace: ${NAMESPACE}
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: ${STORAGE_CLASS}
  resources:
    requests:
      storage: 1Gi
EOF_MANIFEST

printf '🔎 waiting for PVC provisioning\n'
for ((attempt = 1; attempt <= 90; attempt++)); do
  pvc_phase="$(kubectl get pvc "${PVC_NAME}" --namespace "${NAMESPACE}" -o jsonpath='{.status.phase}')"
  [[ "${pvc_phase}" == "Bound" ]] && break
  sleep 1
done
[[ "${pvc_phase:-}" == "Bound" ]] || fail "PVC did not reach Bound state"
pv_name="$(kubectl get pvc "${PVC_NAME}" --namespace "${NAMESPACE}" -o jsonpath='{.spec.volumeName}')"
[[ -n "${pv_name}" ]] || fail "PVC has no bound PersistentVolume"

create_probe_pod() {
  local pod_name="$1"
  local node_name="$2"

  cat <<EOF_MANIFEST | kubectl apply -f - >/dev/null
apiVersion: v1
kind: Pod
metadata:
  name: ${pod_name}
  namespace: ${NAMESPACE}
spec:
  automountServiceAccountToken: false
  nodeName: ${node_name}
  restartPolicy: Never
  securityContext:
    runAsNonRoot: true
    runAsUser: 65532
    runAsGroup: 65532
    fsGroup: 65532
    fsGroupChangePolicy: OnRootMismatch
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: probe
      image: ${IMAGE}
      imagePullPolicy: IfNotPresent
      command: ["sleep", "3600"]
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        readOnlyRootFilesystem: true
      volumeMounts:
        - name: data
          mountPath: /data
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: ${PVC_NAME}
EOF_MANIFEST
}

marker="nabla-persistence-$(date +%s)-$$"
printf '🔎 writing persistent marker on %s\n' "${worker_a_node}"
create_probe_pod writer "${worker_a_node}"
kubectl wait --namespace "${NAMESPACE}" --for=condition=Ready pod/writer --timeout=90s >/dev/null
kubectl exec --namespace "${NAMESPACE}" writer -- \
  sh -c 'printf "%s\n" "$1" > /data/probe.txt && sync' sh "${marker}"
kubectl delete pod writer --namespace "${NAMESPACE}" --wait=true >/dev/null

printf '🔎 recreating consumer on %s and validating persistence\n' "${worker_b_node}"
create_probe_pod reader "${worker_b_node}"
kubectl wait --namespace "${NAMESPACE}" --for=condition=Ready pod/reader --timeout=90s >/dev/null
observed="$(kubectl exec --namespace "${NAMESPACE}" reader -- cat /data/probe.txt)"
[[ "${observed}" == "${marker}" ]] ||
  fail "persistent marker mismatch: expected ${marker}, observed ${observed}"
kubectl delete pod reader --namespace "${NAMESPACE}" --wait=true >/dev/null

printf '🔎 validating smoke PV deprovisioning\n'
kubectl delete pvc "${PVC_NAME}" --namespace "${NAMESPACE}" --wait=true >/dev/null
for ((attempt = 1; attempt <= 90; attempt++)); do
  if ! kubectl get pv "${pv_name}" >/dev/null 2>&1; then
    pv_deleted=true
    break
  fi
  sleep 1
done
[[ "${pv_deleted:-false}" == "true" ]] ||
  fail "smoke PersistentVolume was not deleted after PVC removal: ${pv_name}"

printf '✅ TrueNAS NFS persistence healthy: PVC survived cross-node Pod recreation and smoke PV cleanup succeeded\n'
