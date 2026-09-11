#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
# shellcheck source=scripts/talos/lib/client-config.sh
source "${ROOT}/scripts/talos/lib/client-config.sh"
nabla_resolve_talos_client_config "${ROOT}"
MODE="${1:---check}"
DRIVER_MANIFEST="${ROOT}/kubernetes/truenas-csi/nfs-driver.yaml"
STORAGE_CLASS_MANIFEST="${ROOT}/kubernetes/truenas-csi/storageclass-nfs.yaml"
VERSION_FILE="${ROOT}/kubernetes/truenas-csi/VERSION"
NAMESPACE="truenas-csi"
CREDENTIAL_RESOURCE_NAME="truenas-api-credentials"
CONTROLLER_CLUSTERROLE="truenas-csi-controller-role"
CONTROLLER_SERVICE_ACCOUNT="system:serviceaccount:${NAMESPACE}:truenas-csi-controller-sa"
VOLUME_ATTACHMENT_RESOURCE="volumeattachments.storage.k8s.io"
EXPECTED_VERSION="v1.0.3"
ROLLOUT_TIMEOUT="${CSI_ROLLOUT_TIMEOUT:-180s}"
POD_SECURITY_VERSION="${CSI_POD_SECURITY_VERSION:-v1.36}"
ROTATE_CREDENTIAL="${TRUENAS_CSI_ROTATE_CREDENTIAL:-0}"
FORCE_CREDENTIAL_RELOAD="${TRUENAS_CSI_FORCE_CREDENTIAL_RELOAD:-0}"
credential_changed=false
controller_existed_before_apply=false
node_existed_before_apply=false

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

ok() {
  printf '✅ %s\n' "$*"
}

warn() {
  printf '⚠️  %s\n' "$*" >&2
}

dump_controller_rollout_diagnostics() {
  local pod

  printf '⚠️  TrueNAS CSI controller rollout diagnostics\n' >&2
  kubectl -n "${NAMESPACE}" get deployment,rs,pod \
    -l app=truenas-csi-controller -o wide >&2 2>/dev/null || true
  kubectl -n "${NAMESPACE}" get deployment truenas-csi-controller -o json 2>/dev/null |
    jq '{generation: .metadata.generation, observedGeneration: .status.observedGeneration, desired: .spec.replicas, updated: .status.updatedReplicas, ready: .status.readyReplicas, available: .status.availableReplicas, unavailable: .status.unavailableReplicas, conditions: .status.conditions}' >&2 || true

  while IFS= read -r pod; do
    [[ -n "${pod}" ]] || continue
    printf 'ℹ️  %s container state\n' "${pod}" >&2
    kubectl -n "${NAMESPACE}" get pod "${pod}" -o json 2>/dev/null |
      jq '{name: .metadata.name, created: .metadata.creationTimestamp, node: .spec.nodeName, containers: [.status.containerStatuses[]? | {name, ready, restartCount, state, lastState}]}' >&2 || true
    for container in csi-controller csi-attacher csi-provisioner csi-resizer; do
      if kubectl -n "${NAMESPACE}" get pod "${pod}" \
        -o jsonpath='{.spec.containers[*].name}' 2>/dev/null | grep -qw "${container}"; then
        printf 'ℹ️  %s/%s logs (tail 40)\n' "${pod}" "${container}" >&2
        kubectl -n "${NAMESPACE}" logs "${pod}" -c "${container}" --tail=40 >&2 2>/dev/null || true
      fi
    done
  done < <(
    kubectl -n "${NAMESPACE}" get pods -l app=truenas-csi-controller \
      -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null || true
  )
}

dump_node_rollout_diagnostics() {
  local pod

  printf '⚠️  TrueNAS CSI node rollout diagnostics\n' >&2
  kubectl -n "${NAMESPACE}" get daemonset truenas-csi-node \
    -o custom-columns='NAME:.metadata.name,DESIRED:.status.desiredNumberScheduled,CURRENT:.status.currentNumberScheduled,READY:.status.numberReady,AVAILABLE:.status.numberAvailable,MISSCHEDULED:.status.numberMisscheduled' \
    2>/dev/null || true

  kubectl -n "${NAMESPACE}" get pods -l app=truenas-csi-node -o wide 2>/dev/null || true

  kubectl -n "${NAMESPACE}" get pods -l app=truenas-csi-node \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.nodeName}{"\t"}{range .status.containerStatuses[*]}{.name}={.state.waiting.reason}{.state.terminated.reason}{" restarts="}{.restartCount}{";"}{end}{"\n"}{end}' \
    2>/dev/null || true

  printf 'ℹ️  recent truenas-csi events\n' >&2
  kubectl -n "${NAMESPACE}" get events --sort-by=.lastTimestamp 2>/dev/null |
    tail -n 30 || true

  while IFS= read -r pod; do
    [[ -n "${pod}" ]] || continue
    printf 'ℹ️  %s csi-node logs (tail 40)\n' "${pod}" >&2
    kubectl -n "${NAMESPACE}" logs "${pod}" -c csi-node --tail=40 2>/dev/null || true
    printf 'ℹ️  %s registrar logs (tail 20)\n' "${pod}" >&2
    kubectl -n "${NAMESPACE}" logs "${pod}" -c csi-node-driver-registrar --tail=20 2>/dev/null || true
  done < <(
    kubectl -n "${NAMESPACE}" get pods -l app=truenas-csi-node \
      -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null || true
  )
}

controller_volumeattachment_rbac_ok() {
  local verb

  for verb in get list watch patch; do
    [[ "$(kubectl auth can-i \
      --as="${CONTROLLER_SERVICE_ACCOUNT}" \
      "${verb}" "${VOLUME_ATTACHMENT_RESOURCE}" 2>/dev/null)" == "yes" ]] || return 1
  done

  [[ "$(kubectl auth can-i \
    --as="${CONTROLLER_SERVICE_ACCOUNT}" \
    patch "${VOLUME_ATTACHMENT_RESOURCE}" --subresource=status 2>/dev/null)" == "yes" ]]
}

report_controller_volumeattachment_rbac() {
  local verb result
  local missing=false

  for verb in get list watch patch; do
    result="$(kubectl auth can-i \
      --as="${CONTROLLER_SERVICE_ACCOUNT}" \
      "${verb}" "${VOLUME_ATTACHMENT_RESOURCE}" 2>/dev/null || true)"
    if [[ "${result}" == "yes" ]]; then
      ok "CSI controller RBAC allows ${verb} ${VOLUME_ATTACHMENT_RESOURCE}"
    else
      warn "CSI controller RBAC denies ${verb} ${VOLUME_ATTACHMENT_RESOURCE}"
      missing=true
    fi
  done

  result="$(kubectl auth can-i \
    --as="${CONTROLLER_SERVICE_ACCOUNT}" \
    patch "${VOLUME_ATTACHMENT_RESOURCE}" --subresource=status 2>/dev/null || true)"
  if [[ "${result}" == "yes" ]]; then
    ok "CSI controller RBAC allows patch ${VOLUME_ATTACHMENT_RESOURCE}/status"
  else
    warn "CSI controller RBAC denies patch ${VOLUME_ATTACHMENT_RESOURCE}/status; csi-attacher cannot persist publishContext"
    missing=true
  fi

  [[ "${missing}" == "false" ]]
}

report_attach_contract() {
  local attach_required
  local containers

  if ! kubectl get csidriver csi.truenas.io >/dev/null 2>&1; then
    printf 'ℹ️  CSIDriver csi.truenas.io is not installed yet\n'
    return 0
  fi

  attach_required="$(kubectl get csidriver csi.truenas.io -o jsonpath='{.spec.attachRequired}')"
  if [[ "${attach_required}" == "true" ]]; then
    ok "CSIDriver csi.truenas.io attachRequired=true"
  else
    warn "CSIDriver csi.truenas.io attachRequired=${attach_required:-missing}; ControllerPublishVolume is skipped and NodeStageVolume receives no publishContext"
    return 1
  fi

  if kubectl -n "${NAMESPACE}" get deployment truenas-csi-controller >/dev/null 2>&1; then
    containers="$(kubectl -n "${NAMESPACE}" get deployment truenas-csi-controller -o jsonpath='{.spec.template.spec.containers[*].name}')"
    if [[ " ${containers} " == *" csi-attacher "* ]]; then
      ok "TrueNAS CSI controller includes csi-attacher"
    else
      warn "TrueNAS CSI controller is missing csi-attacher; no component can call ControllerPublishVolume"
      return 1
    fi
  fi
}

controller_runtime_converged() {
  local deployment_json desired updated ready available unavailable generation observed progress_deadline

  if ! kubectl -n "${NAMESPACE}" get deployment truenas-csi-controller >/dev/null 2>&1; then
    return 0
  fi

  deployment_json="$(kubectl -n "${NAMESPACE}" get deployment truenas-csi-controller -o json)"
  desired="$(jq -r '.spec.replicas // 1' <<<"${deployment_json}")"
  updated="$(jq -r '.status.updatedReplicas // 0' <<<"${deployment_json}")"
  ready="$(jq -r '.status.readyReplicas // 0' <<<"${deployment_json}")"
  available="$(jq -r '.status.availableReplicas // 0' <<<"${deployment_json}")"
  unavailable="$(jq -r '.status.unavailableReplicas // 0' <<<"${deployment_json}")"
  generation="$(jq -r '.metadata.generation // 0' <<<"${deployment_json}")"
  observed="$(jq -r '.status.observedGeneration // 0' <<<"${deployment_json}")"
  progress_deadline="$(jq -r '[.status.conditions[]? | select(.type == "Progressing" and .status == "False" and .reason == "ProgressDeadlineExceeded")] | length' <<<"${deployment_json}")"

  [[ "${observed}" -ge "${generation}" &&
     "${updated}" -eq "${desired}" &&
     "${ready}" -eq "${desired}" &&
     "${available}" -eq "${desired}" &&
     "${unavailable}" -eq 0 &&
     "${progress_deadline}" -eq 0 ]]
}

report_controller_runtime() {
  local deployment_json desired updated ready available unavailable

  if ! kubectl -n "${NAMESPACE}" get deployment truenas-csi-controller >/dev/null 2>&1; then
    printf 'ℹ️  TrueNAS CSI controller Deployment is not installed yet\n'
    return 0
  fi

  if controller_runtime_converged; then
    ok "TrueNAS CSI controller Deployment is fully converged"
    return 0
  fi

  deployment_json="$(kubectl -n "${NAMESPACE}" get deployment truenas-csi-controller -o json)"
  desired="$(jq -r '.spec.replicas // 1' <<<"${deployment_json}")"
  updated="$(jq -r '.status.updatedReplicas // 0' <<<"${deployment_json}")"
  ready="$(jq -r '.status.readyReplicas // 0' <<<"${deployment_json}")"
  available="$(jq -r '.status.availableReplicas // 0' <<<"${deployment_json}")"
  unavailable="$(jq -r '.status.unavailableReplicas // 0' <<<"${deployment_json}")"
  warn "TrueNAS CSI controller runtime is not converged: desired=${desired} updated=${updated} ready=${ready} available=${available} unavailable=${unavailable}"
  return 1
}

prepare_immutable_csidriver_migration() {
  local attach_required
  local attachment_count

  if ! kubectl get csidriver csi.truenas.io >/dev/null 2>&1; then
    return
  fi

  attach_required="$(kubectl get csidriver csi.truenas.io -o jsonpath='{.spec.attachRequired}')"
  [[ "${attach_required}" == "true" ]] && return

  [[ "${attach_required}" == "false" ]] ||
    fail "unexpected CSIDriver attachRequired value: ${attach_required:-missing}"

  attachment_count="$(
    kubectl get volumeattachments.storage.k8s.io -o json |
      jq '[.items[] | select(.spec.attacher == "csi.truenas.io")] | length'
  )"
  [[ "${attachment_count}" -eq 0 ]] ||
    fail "cannot recreate immutable CSIDriver while ${attachment_count} TrueNAS VolumeAttachment object(s) exist"

  warn "recreating CSIDriver csi.truenas.io because attachRequired is immutable and the installed value is false"
  kubectl delete csidriver csi.truenas.io --wait=true >/dev/null
  ok "old CSIDriver removed; canonical attachRequired=true object will be recreated"
}

report_namespace_pod_security() {
  local enforce_level=""
  local enforce_version=""
  local audit_level=""
  local warn_level=""

  if ! kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
    printf 'ℹ️  namespace %s does not exist yet; Pod Security labels will be applied during --apply\n' "${NAMESPACE}"
    return
  fi

  enforce_level="$(kubectl get namespace "${NAMESPACE}" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}' 2>/dev/null || true)"
  enforce_version="$(kubectl get namespace "${NAMESPACE}" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce-version}' 2>/dev/null || true)"
  audit_level="$(kubectl get namespace "${NAMESPACE}" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/audit}' 2>/dev/null || true)"
  warn_level="$(kubectl get namespace "${NAMESPACE}" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/warn}' 2>/dev/null || true)"

  if [[ "${enforce_level}" == "privileged" ]]; then
    ok "namespace ${NAMESPACE} Pod Security enforce=privileged version=${enforce_version:-default} audit=${audit_level:-default} warn=${warn_level:-default}"
  else
    warn "namespace ${NAMESPACE} Pod Security enforce=${enforce_level:-cluster-default}; the privileged CSI node DaemonSet can be rejected by baseline/restricted admission"
  fi
}

ensure_namespace_pod_security() {
  local enforce_level
  local enforce_version
  local audit_level
  local warn_level

  if ! kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
    kubectl create namespace "${NAMESPACE}" >/dev/null
  fi

  kubectl label --overwrite namespace "${NAMESPACE}" \
    pod-security.kubernetes.io/enforce=privileged \
    pod-security.kubernetes.io/enforce-version="${POD_SECURITY_VERSION}" \
    pod-security.kubernetes.io/audit=baseline \
    pod-security.kubernetes.io/audit-version="${POD_SECURITY_VERSION}" \
    pod-security.kubernetes.io/warn=baseline \
    pod-security.kubernetes.io/warn-version="${POD_SECURITY_VERSION}" \
    >/dev/null

  enforce_level="$(kubectl get namespace "${NAMESPACE}" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}')"
  enforce_version="$(kubectl get namespace "${NAMESPACE}" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce-version}')"
  audit_level="$(kubectl get namespace "${NAMESPACE}" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/audit}')"
  warn_level="$(kubectl get namespace "${NAMESPACE}" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/warn}')"

  [[ "${enforce_level}" == "privileged" ]] ||
    fail "namespace ${NAMESPACE} must enforce privileged Pod Security for the CSI node plugin"
  [[ "${enforce_version}" == "${POD_SECURITY_VERSION}" ]] ||
    fail "namespace ${NAMESPACE} Pod Security version mismatch: ${enforce_version:-missing}"
  [[ "${audit_level}" == "baseline" && "${warn_level}" == "baseline" ]] ||
    fail "namespace ${NAMESPACE} must retain baseline Pod Security audit/warn visibility"

  ok "namespace ${NAMESPACE} Pod Security configured: enforce=privileged, audit/warn=baseline, version=${POD_SECURITY_VERSION}"
}

reconcile_credential_secret() {
  local candidate_hash existing_hash

  candidate_hash="$(printf '%s' "${TRUENAS_CSI_API_KEY}" | sha256sum | awk '{print $1}')"

  if kubectl -n "${NAMESPACE}" get secret "${CREDENTIAL_RESOURCE_NAME}" >/dev/null 2>&1; then
    existing_hash="$(
      kubectl -n "${NAMESPACE}" get secret "${CREDENTIAL_RESOURCE_NAME}" \
        -o jsonpath='{.data.api-key}' |
        base64 -d |
        sha256sum |
        awk '{print $1}'
    )"
    if [[ "${candidate_hash}" == "${existing_hash}" ]]; then
      ok "CSI credential matches the existing Kubernetes Secret (value not printed)"
      return 0
    fi

    [[ "${ROTATE_CREDENTIAL}" == "1" ]] ||
      fail "TRUENAS_CSI_API_KEY differs from the existing CSI Secret; refusing implicit credential rotation. Review the source secret and set TRUENAS_CSI_ROTATE_CREDENTIAL=1 only for an intentional rotation"
    warn "explicit CSI credential rotation approved; existing Pods will be restarted to reload the Secret"
  else
    printf 'ℹ️  CSI credential Secret does not exist yet; creating initial credential\n'
  fi

  printf '%s' "${TRUENAS_CSI_API_KEY}" |
    kubectl -n "${NAMESPACE}" create secret generic "${CREDENTIAL_RESOURCE_NAME}" \
      --from-file=api-key=/dev/stdin \
      --dry-run=client -o yaml |
    kubectl apply -f - >/dev/null
  credential_changed=true
  ok "CSI credential Secret reconciled without exposing the key in argv or output"
}

reload_credential_consumers_if_needed() {
  local reload=false

  if [[ "${credential_changed}" == "true" || "${FORCE_CREDENTIAL_RELOAD}" == "1" ]]; then
    reload=true
  fi
  [[ "${reload}" == "true" ]] || return 0

  if [[ "${controller_existed_before_apply}" == "true" || "${FORCE_CREDENTIAL_RELOAD}" == "1" ]]; then
    kubectl -n "${NAMESPACE}" rollout restart deployment/truenas-csi-controller >/dev/null
    ok "CSI controller restart requested so TRUENAS_API_KEY is reloaded from the Secret"
  fi
  if [[ "${node_existed_before_apply}" == "true" || "${FORCE_CREDENTIAL_RELOAD}" == "1" ]]; then
    kubectl -n "${NAMESPACE}" rollout restart daemonset/truenas-csi-node >/dev/null
    ok "CSI node restart requested so TRUENAS_API_KEY is reloaded from the Secret"
  fi
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: bash scripts/talos/install-truenas-csi-nfs.sh [--check|--apply]" ;;
esac

for command in kubectl jq; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done
[[ -s "${KUBECONFIG}" ]] || fail "kubeconfig not found: ${KUBECONFIG}"
export KUBECONFIG

[[ -s "${DRIVER_MANIFEST}" ]] || fail "missing driver manifest"
[[ -s "${STORAGE_CLASS_MANIFEST}" ]] || fail "missing StorageClass manifest"
[[ "$(<"${VERSION_FILE}")" == "${EXPECTED_VERSION}" ]] ||
  fail "TrueNAS CSI pin must remain ${EXPECTED_VERSION}"

grep -Fq "ghcr.io/truenas/truenas-csi:${EXPECTED_VERSION}" "${DRIVER_MANIFEST}" ||
  fail "driver image is not pinned to ${EXPECTED_VERSION}"
grep -Fq "registry.k8s.io/sig-storage/csi-attacher:v4.11.0" "${DRIVER_MANIFEST}" ||
  fail "TrueNAS CSI v1.0.3 publishContext path requires csi-attacher:v4.11.0"
if grep -Eq 'truenas-csi:(latest|master|main)' "${DRIVER_MANIFEST}"; then
  fail "floating TrueNAS CSI image tag detected"
fi
if grep -Eq 'iscsiadm|/etc/iscsi|/var/lib/iscsi' "${DRIVER_MANIFEST}"; then
  fail "NFS-only Talos manifest must not require iSCSI host tooling"
fi

kubectl apply --dry-run=client -f "${DRIVER_MANIFEST}" >/dev/null
kubectl apply --dry-run=client -f "${STORAGE_CLASS_MANIFEST}" >/dev/null
ok "tracked TrueNAS CSI NFS manifests pass kubectl client validation"

if [[ "${MODE}" == "--check" ]]; then
  report_namespace_pod_security

  if ! report_attach_contract; then
    fail "installed CSI attach contract is stale; run --apply to migrate immutable attachRequired=false and deploy csi-attacher"
  fi

  if kubectl get storageclass nabla-truenas-nfs >/dev/null 2>&1; then
    ok "StorageClass nabla-truenas-nfs already exists"
  else
    printf 'ℹ️  StorageClass nabla-truenas-nfs is not installed yet\n'
  fi

  if kubectl -n "${NAMESPACE}" get secret "${CREDENTIAL_RESOURCE_NAME}" >/dev/null 2>&1; then
    ok "CSI credential Secret exists (value not read)"
  else
    printf 'ℹ️  CSI credential Secret is not installed yet\n'
  fi

  if kubectl get clusterrole "${CONTROLLER_CLUSTERROLE}" >/dev/null 2>&1; then
    report_controller_volumeattachment_rbac ||
      fail "installed CSI controller RBAC cannot support csi-attacher publishContext persistence; run --apply"
  else
    printf 'ℹ️  CSI controller ClusterRole is not installed yet; --apply will create the publishContext RBAC contract\n'
  fi

  if ! report_controller_runtime; then
    dump_controller_rollout_diagnostics
    fail "installed CSI controller is not runtime-converged; fix authentication/rollout before storage acceptance"
  fi

  printf 'ℹ️  TrueNAS CSI v1.0.3 still uses deprecated auth.login_with_api_key; validate this path on TrueNAS 26 and replace it before TrueNAS 27.\n'
  exit 0
fi

for command in base64 sha256sum awk; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required for credential reconciliation"
done
[[ -n "${TRUENAS_CSI_API_KEY:-}" ]] ||
  fail "TRUENAS_CSI_API_KEY is required for --apply"
[[ "${ROTATE_CREDENTIAL}" =~ ^[01]$ ]] ||
  fail "TRUENAS_CSI_ROTATE_CREDENTIAL must be 0 or 1"
[[ "${FORCE_CREDENTIAL_RELOAD}" =~ ^[01]$ ]] ||
  fail "TRUENAS_CSI_FORCE_CREDENTIAL_RELOAD must be 0 or 1"
if [[ -n "${TRUENAS_CSI_API_USERNAME:-}" ]]; then
  warn "TRUENAS_CSI_API_USERNAME is intentionally not injected: upstream v1.0.3 accepts only TRUENAS_API_KEY and still uses auth.login_with_api_key."
fi

if kubectl -n "${NAMESPACE}" get deployment truenas-csi-controller >/dev/null 2>&1; then
  controller_existed_before_apply=true
fi
if kubectl -n "${NAMESPACE}" get daemonset truenas-csi-node >/dev/null 2>&1; then
  node_existed_before_apply=true
fi

ensure_namespace_pod_security
reconcile_credential_secret

prepare_immutable_csidriver_migration
kubectl apply -f "${DRIVER_MANIFEST}"
report_attach_contract ||
  fail "TrueNAS CSI attach contract did not converge after applying the canonical manifest"
controller_volumeattachment_rbac_ok ||
  fail "TrueNAS CSI controller VolumeAttachment RBAC did not converge after applying the canonical manifest"
ok "CSI controller VolumeAttachment RBAC supports read + patch/status only; create/update/delete remain denied"

reload_credential_consumers_if_needed

if ! kubectl -n "${NAMESPACE}" rollout status deployment/truenas-csi-controller --timeout="${ROLLOUT_TIMEOUT}"; then
  dump_controller_rollout_diagnostics
  fail "TrueNAS CSI controller Deployment did not become Ready within ${ROLLOUT_TIMEOUT}; inspect authentication and socket diagnostics above before retrying"
fi
report_controller_runtime ||
  fail "TrueNAS CSI controller rollout returned but runtime status is not fully converged"

if ! kubectl -n "${NAMESPACE}" rollout status daemonset/truenas-csi-node --timeout="${ROLLOUT_TIMEOUT}"; then
  dump_node_rollout_diagnostics
  fail "TrueNAS CSI node DaemonSet did not become Ready within ${ROLLOUT_TIMEOUT}; inspect the diagnostics above before retrying"
fi

kubectl get csidriver csi.truenas.io >/dev/null
ok "CSIDriver csi.truenas.io registered with controller publish enabled"

kubectl apply -f "${STORAGE_CLASS_MANIFEST}"
default_value="$(kubectl get storageclass nabla-truenas-nfs \
  -o jsonpath='{.metadata.annotations.storageclass\.kubernetes\.io/is-default-class}')"
[[ "${default_value}" == "false" ]] ||
  fail "nabla-truenas-nfs must not be default before persistence acceptance"
ok "StorageClass nabla-truenas-nfs installed and remains non-default"

printf '✅ TrueNAS CSI NFS install complete. Run scripts/talos/smoke-truenas-csi-nfs.sh --apply next.\n'
