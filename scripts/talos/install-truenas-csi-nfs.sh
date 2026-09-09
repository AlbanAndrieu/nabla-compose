#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
KUBECONFIG="${KUBECONFIG:-${ROOT}/.talos/generated/kubeconfig}"
MODE="${1:---check}"
DRIVER_MANIFEST="${ROOT}/kubernetes/truenas-csi/nfs-driver.yaml"
STORAGE_CLASS_MANIFEST="${ROOT}/kubernetes/truenas-csi/storageclass-nfs.yaml"
VERSION_FILE="${ROOT}/kubernetes/truenas-csi/VERSION"
NAMESPACE="truenas-csi"
CREDENTIAL_RESOURCE_NAME="truenas-api-credentials"
EXPECTED_VERSION="v1.0.3"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

ok() {
  printf '✅ %s\n' "$*"
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

kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml |
  kubectl apply -f - >/dev/null

printf '%s' "${TRUENAS_CSI_API_KEY}" |
  kubectl -n "${NAMESPACE}" create secret generic "${CREDENTIAL_RESOURCE_NAME}" \
    --from-file=api-key=/dev/stdin \
    --dry-run=client -o yaml |
  kubectl apply -f - >/dev/null
ok "CSI credential Secret reconciled without exposing the key in argv or output"

kubectl apply -f "${DRIVER_MANIFEST}"
kubectl -n "${NAMESPACE}" rollout status deployment/truenas-csi-controller --timeout=180s
kubectl -n "${NAMESPACE}" rollout status daemonset/truenas-csi-node --timeout=180s

kubectl get csidriver csi.truenas.io >/dev/null
ok "CSIDriver csi.truenas.io registered"

kubectl apply -f "${STORAGE_CLASS_MANIFEST}"
default_value="$(kubectl get storageclass nabla-truenas-nfs   -o jsonpath='{.metadata.annotations.storageclass\.kubernetes\.io/is-default-class}')"
[[ "${default_value}" == "false" ]] ||
  fail "nabla-truenas-nfs must not be default before persistence acceptance"
ok "StorageClass nabla-truenas-nfs installed and remains non-default"

printf '✅ TrueNAS CSI NFS install complete. Run scripts/talos/smoke-truenas-csi-nfs.sh --apply next.\n'
