#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
# shellcheck source=scripts/talos/lib/client-config.sh
source "${ROOT}/scripts/talos/lib/client-config.sh"
# shellcheck source=scripts/lib/truenas.sh
source "${ROOT}/scripts/lib/truenas.sh"
# Shared TrueNAS helpers own the pool.dataset.query and sharing.nfs.query calls used below.
nabla_resolve_talos_client_config "${ROOT}"
MODE="--check"
KEEP=false
CLEANUP_DONE=false
NAMESPACE="nabla-csi-smoke"
PVC="nabla-csi-rwx"
STORAGE_CLASS="nabla-truenas-nfs"
MARKER="nabla-truenas-csi-cross-node-v1"
SMOKE_IMAGE="${CSI_SMOKE_IMAGE:-busybox@sha256:9532d8c39891ca2ecde4d30d7710e01fb739c87a8b9299685c63704296b16028}"
PVC_TIMEOUT_SECONDS="${CSI_PVC_TIMEOUT_SECONDS:-180}"
ATTACH_TIMEOUT_SECONDS="${CSI_ATTACHMENT_TIMEOUT_SECONDS:-60}"
POD_READY_TIMEOUT_SECONDS="${CSI_POD_READY_TIMEOUT_SECONDS:-300}"
NAMESPACE_DELETE_TIMEOUT_SECONDS="${CSI_NAMESPACE_DELETE_TIMEOUT_SECONDS:-120}"
DIAGNOSTIC_TAIL="${CSI_DIAGNOSTIC_TAIL:-100}"
KEEP_ON_FAILURE="${CSI_SMOKE_KEEP_ON_FAILURE:-false}"
TRUENAS_RECLAIM_TIMEOUT_SECONDS="${CSI_TRUENAS_RECLAIM_TIMEOUT_SECONDS:-120}"

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

[[ "${PVC_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] ||
  fail "CSI_PVC_TIMEOUT_SECONDS must be a positive integer"
[[ "${ATTACH_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] ||
  fail "CSI_ATTACHMENT_TIMEOUT_SECONDS must be a positive integer"
[[ "${POD_READY_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] ||
  fail "CSI_POD_READY_TIMEOUT_SECONDS must be a positive integer"
[[ "${NAMESPACE_DELETE_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] ||
  fail "CSI_NAMESPACE_DELETE_TIMEOUT_SECONDS must be a positive integer"
[[ "${DIAGNOSTIC_TAIL}" =~ ^[1-9][0-9]*$ ]] ||
  fail "CSI_DIAGNOSTIC_TAIL must be a positive integer"
[[ "${TRUENAS_RECLAIM_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] ||
  fail "CSI_TRUENAS_RECLAIM_TIMEOUT_SECONDS must be a positive integer"

for command in kubectl jq; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done
if [[ "${MODE}" == "--apply" && "${KEEP}" != "true" ]]; then
  for command in midclt zfs; do
    command -v "${command}" >/dev/null 2>&1 ||
      fail "${command} is required for authoritative TrueNAS reclaim verification; run the apply smoke from the TrueNAS operator environment"
  done
fi
[[ -s "${KUBECONFIG}" ]] || fail "kubeconfig not found: ${KUBECONFIG}"
export KUBECONFIG

kubectl get csidriver csi.truenas.io >/dev/null ||
  fail "CSIDriver csi.truenas.io is not registered"
attach_required="$(kubectl get csidriver csi.truenas.io -o jsonpath='{.spec.attachRequired}')"
[[ "${attach_required}" == "true" ]] ||
  fail "CSIDriver csi.truenas.io attachRequired=${attach_required:-missing}; ControllerPublishVolume is skipped and publishContext cannot reach NodeStageVolume"
kubectl get storageclass "${STORAGE_CLASS}" >/dev/null ||
  fail "StorageClass ${STORAGE_CLASS} is not installed"
kubectl -n truenas-csi rollout status deployment/truenas-csi-controller --timeout=30s >/dev/null
controller_containers="$(kubectl -n truenas-csi get deployment truenas-csi-controller -o jsonpath='{.spec.template.spec.containers[*].name}')"
[[ " ${controller_containers} " == *" csi-attacher "* ]] ||
  fail "TrueNAS CSI controller is missing csi-attacher; ControllerPublishVolume cannot populate publishContext"
kubectl -n truenas-csi rollout status daemonset/truenas-csi-node --timeout=30s >/dev/null
ok "TrueNAS CSI controller, attacher, node plugin and StorageClass are ready"

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
  if command -v midclt >/dev/null 2>&1 && command -v zfs >/dev/null 2>&1; then
    ok "authoritative TrueNAS reclaim verification tools are available for --apply"
  else
    printf 'ℹ️  midclt/zfs are unavailable here; run --apply without --keep from the TrueNAS operator environment so final reclaim can be proven\n'
  fi
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

truenas_reclaim_state() {
  local dataset="$1"
  local share_path="$2"
  local dataset_json dataset_count nfs_count zfs_exists

  dataset_json="$(truenas_dataset_query_by_id "${dataset}" 2>/dev/null)" ||
    fail "TrueNAS dataset API query failed while verifying reclaim for ${dataset}"
  dataset_count="$(jq 'length' <<<"${dataset_json}")"

  nfs_count="$(truenas_nfs_share_count_for_path "${share_path}" 2>/dev/null)" ||
    fail "TrueNAS NFS share API query failed while verifying reclaim for ${share_path}"

  if zfs list -H -o name "${dataset}" >/dev/null 2>&1; then
    zfs_exists=1
  else
    zfs_exists=0
  fi

  printf '%s\t%s\t%s\n' "${dataset_count}" "${nfs_count}" "${zfs_exists}"
}

wait_for_truenas_reclaim() {
  local dataset="$1"
  local share_path="$2"
  local deadline state dataset_count nfs_count zfs_exists

  deadline=$((SECONDS + TRUENAS_RECLAIM_TIMEOUT_SECONDS))
  while ((SECONDS < deadline)); do
    state="$(truenas_reclaim_state "${dataset}" "${share_path}")"
    IFS="$(printf '\t')" read -r dataset_count nfs_count zfs_exists <<<"${state}"
    if [[ "${dataset_count}" == "0" && "${nfs_count}" == "0" && "${zfs_exists}" == "0" ]]; then
      ok "TrueNAS reclaim postcondition satisfied: dataset, NFS share and ZFS resource are absent"
      return 0
    fi
    sleep 2
  done

  state="$(truenas_reclaim_state "${dataset}" "${share_path}")"
  IFS="$(printf '\t')" read -r dataset_count nfs_count zfs_exists <<<"${state}"
  fail "TrueNAS reclaim postcondition failed after ${TRUENAS_RECLAIM_TIMEOUT_SECONDS}s: dataset=${dataset} middleware_dataset_count=${dataset_count} nfs_share_count=${nfs_count} zfs_exists=${zfs_exists}; do not trust DeleteVolume/API success alone (NAS-143316)"
}

dump_pvc_provisioning_diagnostics() {
  local controller_pod

  printf '\n🔎 TrueNAS CSI PVC provisioning diagnostics\n' >&2
  printf '%s\n' '--- PVC ---' >&2
  kubectl -n "${NAMESPACE}" get pvc "${PVC}" -o wide >&2 || true
  kubectl -n "${NAMESPACE}" describe pvc "${PVC}" 2>&1 |
    tail -n "${DIAGNOSTIC_TAIL}" >&2 || true

  printf '%s\n' '--- recent smoke namespace events ---' >&2
  kubectl -n "${NAMESPACE}" get events --sort-by=.lastTimestamp 2>&1 |
    tail -n 30 >&2 || true

  printf '%s\n' '--- CSI controller pod ---' >&2
  kubectl -n truenas-csi get pods -l app=truenas-csi-controller -o wide >&2 || true
  controller_pod="$(
    kubectl -n truenas-csi get pods -l app=truenas-csi-controller \
      -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true
  )"
  if [[ -z "${controller_pod}" ]]; then
    printf '⚠️  no TrueNAS CSI controller pod found for log collection\n' >&2
    return
  fi

  printf '%s\n' '--- csi-provisioner logs ---' >&2
  kubectl -n truenas-csi logs "${controller_pod}" -c csi-provisioner \
    --since=15m --tail="${DIAGNOSTIC_TAIL}" >&2 || true

  printf '%s\n' '--- TrueNAS csi-controller logs ---' >&2
  kubectl -n truenas-csi logs "${controller_pod}" -c csi-controller \
    --since=15m --tail="${DIAGNOSTIC_TAIL}" >&2 || true
}

dump_publish_context_diagnostics() {
  local pv_name="$1"
  local node_name="$2"

  printf '\n🔎 TrueNAS CSI controller publish diagnostics: PV=%s node=%s\n' "${pv_name}" "${node_name}" >&2
  printf '%s\n' '--- matching VolumeAttachments ---' >&2
  kubectl get volumeattachments.storage.k8s.io -o json 2>/dev/null |
    jq --arg pv "${pv_name}" --arg node "${node_name}" '
      .items[]
      | select(.spec.source.persistentVolumeName == $pv and .spec.nodeName == $node)
      | {
          name: .metadata.name,
          attacher: .spec.attacher,
          nodeName: .spec.nodeName,
          attached: .status.attached,
          attachmentMetadata: .status.attachmentMetadata,
          attachError: .status.attachError,
          detachError: .status.detachError
        }
    ' >&2 || true

  printf '%s\n' '--- csi-attacher logs ---' >&2
  kubectl -n truenas-csi logs deployment/truenas-csi-controller -c csi-attacher \
    --since=10m --tail="${DIAGNOSTIC_TAIL}" >&2 || true

  printf '%s\n' '--- TrueNAS csi-controller logs ---' >&2
  kubectl -n truenas-csi logs deployment/truenas-csi-controller -c csi-controller \
    --since=10m --tail="${DIAGNOSTIC_TAIL}" >&2 || true
}

wait_for_nfs_publish_context() {
  local pv_name="$1"
  local node_name="$2"
  local attachment=""
  local attachment_json=""
  local attached="false"
  local protocol=""
  local nfs_server=""
  local nfs_path=""
  local deadline

  deadline=$((SECONDS + ATTACH_TIMEOUT_SECONDS))
  while ((SECONDS < deadline)); do
    attachment="$(
      kubectl get volumeattachments.storage.k8s.io -o json 2>/dev/null |
        jq -r --arg pv "${pv_name}" --arg node "${node_name}" '
          .items[]
          | select(
              .spec.attacher == "csi.truenas.io"
              and .spec.source.persistentVolumeName == $pv
              and .spec.nodeName == $node
            )
          | .metadata.name
        ' |
        head -n 1
    )"

    if [[ -n "${attachment}" ]]; then
      attachment_json="$(kubectl get volumeattachment "${attachment}" -o json 2>/dev/null || true)"
      if [[ -n "${attachment_json}" ]]; then
        attached="$(jq -r '.status.attached // false' <<<"${attachment_json}")"
        protocol="$(jq -r '.status.attachmentMetadata.protocol // empty' <<<"${attachment_json}")"
        nfs_server="$(jq -r '.status.attachmentMetadata.nfsServer // empty' <<<"${attachment_json}")"
        nfs_path="$(jq -r '.status.attachmentMetadata.nfsPath // empty' <<<"${attachment_json}")"
        if [[ "${attached}" == "true" && "${protocol}" == "nfs" && -n "${nfs_server}" && -n "${nfs_path}" ]]; then
          ok "publishContext ready for ${node_name}: protocol=${protocol} server=${nfs_server} path=${nfs_path}"
          return 0
        fi
      fi
    fi
    sleep 2
  done

  if [[ "${KEEP_ON_FAILURE}" == "true" ]]; then
    KEEP=true
    printf 'ℹ️  CSI_SMOKE_KEEP_ON_FAILURE=true; namespace %s retained for publishContext inspection\n' "${NAMESPACE}" >&2
  fi
  dump_publish_context_diagnostics "${pv_name}" "${node_name}"
  fail "NFS publishContext was not ready within ${ATTACH_TIMEOUT_SECONDS}s for ${node_name}; expected attached=true plus protocol/nfsServer/nfsPath"
}

dump_pod_startup_diagnostics() {
  local pod_name="$1"
  local node_name="$2"
  local node_csi_pod

  printf '\n🔎 TrueNAS CSI pod startup/mount diagnostics: %s on %s\n' "${pod_name}" "${node_name}" >&2
  printf '%s\n' '--- pod ---' >&2
  kubectl -n "${NAMESPACE}" get pod "${pod_name}" -o wide >&2 || true
  kubectl -n "${NAMESPACE}" describe pod "${pod_name}" 2>&1 |
    tail -n "${DIAGNOSTIC_TAIL}" >&2 || true

  printf '%s\n' '--- recent smoke namespace events ---' >&2
  kubectl -n "${NAMESPACE}" get events --sort-by=.lastTimestamp 2>&1 |
    tail -n 40 >&2 || true

  node_csi_pod="$(
    kubectl -n truenas-csi get pods -l app=truenas-csi-node -o json 2>/dev/null |
      jq -r --arg node "${node_name}" '.items[] | select(.spec.nodeName == $node) | .metadata.name' |
      head -n 1
  )"
  if [[ -n "${node_csi_pod}" ]]; then
    printf '%s\n' "--- CSI node logs (${node_csi_pod}) ---" >&2
    kubectl -n truenas-csi logs "${node_csi_pod}" -c csi-node \
      --since=15m --tail="${DIAGNOSTIC_TAIL}" >&2 || true
    printf '%s\n' "--- CSI registrar logs (${node_csi_pod}) ---" >&2
    kubectl -n truenas-csi logs "${node_csi_pod}" -c csi-node-driver-registrar \
      --since=15m --tail="${DIAGNOSTIC_TAIL}" >&2 || true
  else
    printf '⚠️  no TrueNAS CSI node pod found on %s\n' "${node_name}" >&2
  fi
}

dump_cleanup_diagnostics() {
  local pv_name="$1"

  printf '\n🔎 TrueNAS CSI namespace/reclaim diagnostics\n' >&2
  printf '%s\n' '--- namespace termination ---' >&2
  kubectl get namespace "${NAMESPACE}" -o json 2>/dev/null |
    jq '{name: .metadata.name, deletionTimestamp: .metadata.deletionTimestamp, finalizers: .spec.finalizers, conditions: .status.conditions}' >&2 || true

  printf '%s\n' '--- remaining namespace resources ---' >&2
  kubectl -n "${NAMESPACE}" get pvc,pod -o wide >&2 2>/dev/null || true

  printf '%s\n' '--- persistent volume ---' >&2
  kubectl get pv "${pv_name}" -o json 2>/dev/null |
    jq '{name: .metadata.name, deletionTimestamp: .metadata.deletionTimestamp, finalizers: .metadata.finalizers, phase: .status.phase, claimRef: .spec.claimRef, reclaimPolicy: .spec.persistentVolumeReclaimPolicy, volumeHandle: .spec.csi.volumeHandle}' >&2 || true
  kubectl describe pv "${pv_name}" 2>&1 | tail -n "${DIAGNOSTIC_TAIL}" >&2 || true

  printf '%s\n' '--- recent CSI provisioner logs ---' >&2
  kubectl -n truenas-csi logs deployment/truenas-csi-controller -c csi-provisioner \
    --since=10m --tail="${DIAGNOSTIC_TAIL}" >&2 || true

  printf '%s\n' '--- recent CSI attacher logs ---' >&2
  kubectl -n truenas-csi logs deployment/truenas-csi-controller -c csi-attacher \
    --since=10m --tail="${DIAGNOSTIC_TAIL}" >&2 || true

  printf '%s\n' '--- recent TrueNAS CSI controller logs ---' >&2
  kubectl -n truenas-csi logs deployment/truenas-csi-controller -c csi-controller \
    --since=10m --tail="${DIAGNOSTIC_TAIL}" >&2 || true
}

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
deadline=$((SECONDS + PVC_TIMEOUT_SECONDS))
while ((SECONDS < deadline)); do
  phase="$(kubectl -n "${NAMESPACE}" get pvc "${PVC}" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  [[ "${phase}" == "Bound" ]] && break
  sleep 2
done
if [[ "${phase}" != "Bound" ]]; then
  dump_pvc_provisioning_diagnostics
  if [[ "${KEEP_ON_FAILURE}" == "true" ]]; then
    KEEP=true
    printf 'ℹ️  CSI_SMOKE_KEEP_ON_FAILURE=true; namespace %s retained for inspection\n' "${NAMESPACE}" >&2
  fi
  fail "PVC did not become Bound within ${PVC_TIMEOUT_SECONDS}s; inspect ProvisioningFailed events and CSI controller logs above"
fi

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
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    runAsGroup: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: writer
      image: ${SMOKE_IMAGE}
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop:
            - ALL
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

wait_for_nfs_publish_context "${pv}" "${writer_node}"
if ! kubectl -n "${NAMESPACE}" wait --for=condition=Ready pod/csi-writer \
  --timeout="${POD_READY_TIMEOUT_SECONDS}s"; then
  if [[ "${KEEP_ON_FAILURE}" == "true" ]]; then
    KEEP=true
    printf 'ℹ️  CSI_SMOKE_KEEP_ON_FAILURE=true; namespace %s retained for inspection\n' "${NAMESPACE}" >&2
  fi
  dump_pod_startup_diagnostics csi-writer "${writer_node}"
  fail "writer pod did not become Ready within ${POD_READY_TIMEOUT_SECONDS}s; inspect mount/events and CSI node logs above"
fi
writer_value="$(kubectl -n "${NAMESPACE}" exec csi-writer -- cat /data/marker)"
[[ "${writer_value}" == "${MARKER}" ]] || fail "writer marker verification failed"
ok "marker written on ${writer_node}"

kubectl -n "${NAMESPACE}" delete pod csi-writer --wait=true \
  --timeout="${POD_READY_TIMEOUT_SECONDS}s" >/dev/null

cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: csi-reader
  namespace: ${NAMESPACE}
spec:
  nodeName: ${reader_node}
  restartPolicy: Never
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    runAsGroup: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: reader
      image: ${SMOKE_IMAGE}
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop:
            - ALL
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

wait_for_nfs_publish_context "${pv}" "${reader_node}"
if ! kubectl -n "${NAMESPACE}" wait --for=condition=Ready pod/csi-reader \
  --timeout="${POD_READY_TIMEOUT_SECONDS}s"; then
  if [[ "${KEEP_ON_FAILURE}" == "true" ]]; then
    KEEP=true
    printf 'ℹ️  CSI_SMOKE_KEEP_ON_FAILURE=true; namespace %s retained for inspection\n' "${NAMESPACE}" >&2
  fi
  dump_pod_startup_diagnostics csi-reader "${reader_node}"
  fail "reader pod did not become Ready within ${POD_READY_TIMEOUT_SECONDS}s; inspect mount/events and CSI node logs above"
fi
reader_value="$(kubectl -n "${NAMESPACE}" exec csi-reader -- cat /data/marker)"
[[ "${reader_value}" == "${MARKER}" ]] || fail "reader marker verification failed"
ok "marker persisted and was read from different worker ${reader_node}"

if [[ "${KEEP}" == "true" ]]; then
  printf 'ℹ️  retained TrueNAS dataset=%s share_path=%s for inspection\n' \
    "${volume_handle}" "${truenas_share_path}"
  printf '✅ TrueNAS NFS CSI persistence smoke passed with resources retained: PVC Bound, write on %s, read on %s.\n' \
    "${writer_node}" "${reader_node}"
  exit 0
fi

printf '🔎 deleting disposable CSI smoke namespace and waiting up to %ss for namespace termination\n' \
  "${NAMESPACE_DELETE_TIMEOUT_SECONDS}"
kubectl delete namespace "${NAMESPACE}" --wait=false >/dev/null
namespace_deleted=false
deadline=$((SECONDS + NAMESPACE_DELETE_TIMEOUT_SECONDS))
while ((SECONDS < deadline)); do
  if ! kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
    namespace_deleted=true
    break
  fi
  sleep 2
done
if [[ "${namespace_deleted}" != "true" ]]; then
  KEEP=true
  dump_cleanup_diagnostics "${pv}"
  fail "namespace ${NAMESPACE} did not terminate within ${NAMESPACE_DELETE_TIMEOUT_SECONDS}s; retained current state for finalizer/reclaim diagnosis"
fi
CLEANUP_DONE=true
ok "smoke namespace ${NAMESPACE} terminated"

pv_deleted=false
for _ in $(seq 1 90); do
  if ! kubectl get pv "${pv}" >/dev/null 2>&1; then
    pv_deleted=true
    break
  fi
  sleep 2
done
if [[ "${pv_deleted}" != "true" ]]; then
  dump_cleanup_diagnostics "${pv}"
  fail "PV ${pv} was not reclaimed after namespace/PVC deletion"
fi
ok "Kubernetes PV ${pv} reclaimed after PVC deletion"

printf '🔎 verifying TrueNAS reclaim postcondition for dataset=%s share_path=%s (timeout=%ss)\n' \
  "${volume_handle}" "${truenas_share_path}" "${TRUENAS_RECLAIM_TIMEOUT_SECONDS}"
wait_for_truenas_reclaim "${volume_handle}" "${truenas_share_path}"

printf '✅ TrueNAS NFS CSI persistence smoke passed: PVC Bound, write on %s, read on %s, Kubernetes PV reclaimed, TrueNAS dataset/share/ZFS resource absent.\n' \
  "${writer_node}" "${reader_node}"
