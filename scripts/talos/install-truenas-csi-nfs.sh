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
EXPECTED_VERSION="v1.0.3"
ROLLOUT_TIMEOUT="${CSI_ROLLOUT_TIMEOUT:-180s}"
POD_SECURITY_VERSION="${CSI_POD_SECURITY_VERSION:-v1.36}"

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

  # The CSI node plugin must mount kubelet host paths and run privileged. Keep
  # that exception scoped to this infrastructure namespace only. Baseline
  # remains enabled in audit/warn modes so privilege use stays visible.
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

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: bash scripts/talos/install-truenas-csi-nfs.sh [--check|--apply]" ;;
esac

command -v kubectl >/dev/null 2>&1 || fail "kubectl is required"
[[ -s "${KUBECONFIG}" ]] || fail "kubeconfig not found: ${KUBECONFIG}"
export KUBECONFIG

[[ -s "${DRIVER_MANIFEST}" ]] || fail "missing driver manifest"
[[ -s "${STORAGE_CLASS_MANIFEST}" ]] || fail "missing StorageClass manifest"
[[ "$(<"${VERSION_FILE}")" == "${EXPECTED_VERSION}" ]] ||
  fail "TrueNAS CSI pin must remain ${EXPECTED_VERSION}"

grep -Fq "ghcr.io/truenas/truenas-csi:${EXPECTED_VERSION}" "${DRIVER_MANIFEST}" ||
  fail "driver image is not pinned to ${EXPECTED_VERSION}"
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

  if kubectl get csidriver csi.truenas.io >/dev/null 2>&1; then
    ok "CSIDriver csi.truenas.io is already registered"
  else
    printf 'ℹ️  CSIDriver csi.truenas.io is not installed yet\n'
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

  printf 'ℹ️  TrueNAS CSI v1.0.3 still uses deprecated auth.login_with_api_key; validate this path on TrueNAS 26 and replace it before TrueNAS 27.\n'
  exit 0
fi

[[ -n "${TRUENAS_CSI_API_KEY:-}" ]] ||
  fail "TRUENAS_CSI_API_KEY is required for --apply"
if [[ -n "${TRUENAS_CSI_API_USERNAME:-}" ]]; then
  printf '⚠️  TRUENAS_CSI_API_USERNAME is intentionally not injected: upstream v1.0.3 accepts only TRUENAS_API_KEY and still uses auth.login_with_api_key.\n'
fi

ensure_namespace_pod_security

printf '%s' "${TRUENAS_CSI_API_KEY}" |
  kubectl -n "${NAMESPACE}" create secret generic "${CREDENTIAL_RESOURCE_NAME}" \
    --from-file=api-key=/dev/stdin \
    --dry-run=client -o yaml |
  kubectl apply -f - >/dev/null
ok "CSI credential Secret reconciled without exposing the key in argv or output"

kubectl apply -f "${DRIVER_MANIFEST}"
kubectl -n "${NAMESPACE}" rollout status deployment/truenas-csi-controller --timeout="${ROLLOUT_TIMEOUT}"
if ! kubectl -n "${NAMESPACE}" rollout status daemonset/truenas-csi-node --timeout="${ROLLOUT_TIMEOUT}"; then
  dump_node_rollout_diagnostics
  fail "TrueNAS CSI node DaemonSet did not become Ready within ${ROLLOUT_TIMEOUT}; inspect the diagnostics above before retrying"
fi

kubectl get csidriver csi.truenas.io >/dev/null
ok "CSIDriver csi.truenas.io registered"

kubectl apply -f "${STORAGE_CLASS_MANIFEST}"
default_value="$(kubectl get storageclass nabla-truenas-nfs \
  -o jsonpath='{.metadata.annotations.storageclass\.kubernetes\.io/is-default-class}')"
[[ "${default_value}" == "false" ]] ||
  fail "nabla-truenas-nfs must not be default before persistence acceptance"
ok "StorageClass nabla-truenas-nfs installed and remains non-default"

printf '✅ TrueNAS CSI NFS install complete. Run scripts/talos/smoke-truenas-csi-nfs.sh --apply next.\n'
