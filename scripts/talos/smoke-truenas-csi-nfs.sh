#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
# shellcheck source=scripts/talos/lib/client-config.sh
source "${ROOT}/scripts/talos/lib/client-config.sh"
nabla_resolve_talos_client_config "${ROOT}"
MODE="--check"
KEEP=false
CLEANUP_DONE=false
NAMESPACE="nabla-csi-smoke"
PVC="nabla-csi-rwx"
STORAGE_CLASS="nabla-truenas-nfs"
MARKER="nabla-truenas-csi-cross-node-v1"
SMOKE_IMAGE="${CSI_SMOKE_IMAGE:-busybox@sha256:9532d8c39891ca2ecde4d30d7710e01fb739c87a8b9299685c63704296b16028}"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

ok() {
  printf '✅ %s\n' "$*"
}

for arg in "$@"; do
  case "${arg}" in
    --check | --apply) MODE="${arg}" ;;
    --keep) KEEP=true ;;
    *) fail "usage: bash scripts/talos/smoke-truenas-csi-nfs.sh [--check|--apply] [--keep]" ;;
  esac
done

for command in kubectl jq; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done
[[ -s "${KUBECONFIG}" ]] || fail "kubeconfig not found: ${KUBECONFIG}"
export KUBECONFIG

kubectl get csidriver csi.truenas.io >/dev/null ||
  fail "CSIDriver csi.truenas.io is not registered"
kubectl get storageclass "${STORAGE_CLASS}" >/dev/null ||
  fail "StorageClass ${STORAGE_CLASS} is not installed"
kubectl -n truenas-csi rollout status deployment/truenas-csi-controller --timeout=30s >/dev/null
kubectl -n truenas-csi rollout status daemonset/truenas-csi-node --timeout=30s >/dev/null
ok "TrueNAS CSI controller, node plugin and StorageClass are ready"

workers_json="$(kubectl get nodes -o json)"
mapfile -t workers < <(
  jq -r '
    .items[]
    | select(.metadata.labels["node-role.kubernetes.io/control-plane"] == null)
    | select(
        [.status.conditions[]? | select(.type == "Ready" and .status == "True")]
        | length > 0
      )
    | .metadata.name
  ' <<<"${workers_json}"
)
if (("${#workers[@]}" < 2)); then
  fail "cross-node persistence smoke requires at least two Ready worker nodes"
fi

writer_node="${workers[0]}"
reader_node="${workers[1]}"
[[ "${writer_node}" != "${reader_node}" ]] ||
  fail "writer and reader nodes must differ"
ok "cross-node targets selected: writer=${writer_node}, reader=${reader_node}"

if [[ "${MODE}" == "--check" ]]; then
  printf 'ℹ️  --check is read-only. Use --apply to create the disposable PVC and two smoke Pods.\n'
  exit 0
fi

cleanup() {
  if [[ "${KEEP}" == "true" ]]; then
    printf 'ℹ️  --keep selected; namespace %s retained for inspection\n' "${NAMESPACE}"
    return
  fi
  if [[ "${CLEANUP_DONE}" != "true" ]]; then
    kubectl delete namespace "${NAMESPACE}" --wait=false >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml |
  kubectl apply -f - >/dev/null

cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ${PVC}
  namespace: ${NAMESPACE}
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: ${STORAGE_CLASS}
  resources:
    requests:
      storage: 1Gi
EOF

phase=""
for _ in $(seq 1 90); do
  phase="$(kubectl -n "${NAMESPACE}" get pvc "${PVC}" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  [[ "${phase}" == "Bound" ]] && break
  sleep 2
done
[[ "${phase}" == "Bound" ]] || fail "PVC did not become Bound"
pv="$(kubectl -n "${NAMESPACE}" get pvc "${PVC}" -o jsonpath='{.spec.volumeName}')"
volume_handle="$(kubectl get pv "${pv}" -o jsonpath='{.spec.csi.volumeHandle}')"
[[ "${volume_handle}" == cpool/k8s/csi/* ]] ||
  fail "unexpected TrueNAS CSI volumeHandle: ${volume_handle:-missing}"
truenas_share_path="/mnt/${volume_handle}"
ok "PVC ${PVC} is Bound to ${pv}"
ok "TrueNAS volume handle: ${volume_handle}"

cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: csi-writer
  namespace: ${NAMESPACE}
spec:
  nodeName: ${writer_node}
  restartPolicy: Never
  containers:
    - name: writer
      image: ${SMOKE_IMAGE}
      command:
        - sh
        - -c
        - |
          set -eu
          printf '%s\n' '${MARKER}' > /data/marker
          sync
          sleep 3600
      volumeMounts:
        - name: data
          mountPath: /data
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: ${PVC}
EOF

kubectl -n "${NAMESPACE}" wait --for=condition=Ready pod/csi-writer --timeout=120s
writer_value="$(kubectl -n "${NAMESPACE}" exec csi-writer -- cat /data/marker)"
[[ "${writer_value}" == "${MARKER}" ]] || fail "writer marker verification failed"
ok "marker written on ${writer_node}"

kubectl -n "${NAMESPACE}" delete pod csi-writer --wait=true >/dev/null

cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: csi-reader
  namespace: ${NAMESPACE}
spec:
  nodeName: ${reader_node}
  restartPolicy: Never
  containers:
    - name: reader
      image: ${SMOKE_IMAGE}
      command:
        - sh
        - -c
        - |
          set -eu
          test "\$(cat /data/marker)" = '${MARKER}'
          sleep 3600
      volumeMounts:
        - name: data
          mountPath: /data
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: ${PVC}
EOF

kubectl -n "${NAMESPACE}" wait --for=condition=Ready pod/csi-reader --timeout=120s
reader_value="$(kubectl -n "${NAMESPACE}" exec csi-reader -- cat /data/marker)"
[[ "${reader_value}" == "${MARKER}" ]] || fail "reader marker verification failed"
ok "marker persisted and was read from different worker ${reader_node}"

if [[ "${KEEP}" == "true" ]]; then
  printf 'ℹ️  retained TrueNAS dataset=%s share_path=%s for inspection\n'     "${volume_handle}" "${truenas_share_path}"
  printf '✅ TrueNAS NFS CSI persistence smoke passed with resources retained: PVC Bound, write on %s, read on %s.\n'     "${writer_node}" "${reader_node}"
  exit 0
fi

printf '🔎 deleting disposable CSI smoke namespace and waiting for PV reclaim\n'
kubectl delete namespace "${NAMESPACE}" --wait=true >/dev/null
CLEANUP_DONE=true

pv_deleted=false
for _ in $(seq 1 90); do
  if ! kubectl get pv "${pv}" >/dev/null 2>&1; then
    pv_deleted=true
    break
  fi
  sleep 2
done
[[ "${pv_deleted}" == "true" ]] ||
  fail "PV ${pv} was not reclaimed after namespace/PVC deletion"
ok "Kubernetes PV ${pv} reclaimed after PVC deletion"

printf 'ℹ️  verify TrueNAS reclaim: dataset=%s share_path=%s\n'   "${volume_handle}" "${truenas_share_path}"
printf '✅ TrueNAS NFS CSI persistence smoke passed: PVC Bound, write on %s, read on %s, Kubernetes PV reclaimed.\n'   "${writer_node}" "${reader_node}"
