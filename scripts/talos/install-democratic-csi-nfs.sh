#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
KUBECONFIG="${KUBECONFIG:-${ROOT}/.talos/generated/kubeconfig}"
VALUES="${ROOT}/kubernetes/storage/democratic-csi-nfs/values.yaml"
NAMESPACE_MANIFEST="${ROOT}/kubernetes/storage/democratic-csi-nfs/namespace.yaml"
NAMESPACE="${DEMOCRATIC_CSI_NAMESPACE:-democratic-csi}"
RELEASE="${DEMOCRATIC_CSI_RELEASE:-democratic-csi-nfs}"
CHART_VERSION="${DEMOCRATIC_CSI_CHART_VERSION:-0.15.1}"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

for command in helm kubectl; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ -s "${KUBECONFIG}" ]] || fail "Kubeconfig not found: ${KUBECONFIG}"
[[ -s "${VALUES}" ]] || fail "Helm values not found: ${VALUES}"
[[ -s "${NAMESPACE_MANIFEST}" ]] || fail "Namespace manifest not found: ${NAMESPACE_MANIFEST}"
export KUBECONFIG

printf '🔎 validating Kubernetes API before democratic-csi install\n'
kubectl get --raw='/readyz' >/dev/null || fail "Kubernetes API readyz failed"

printf '🔎 applying privileged CSI namespace %s\n' "${NAMESPACE}"
kubectl apply -f "${NAMESPACE_MANIFEST}" >/dev/null

printf '🔎 installing democratic-csi chart %s\n' "${CHART_VERSION}"
helm repo add democratic-csi https://democratic-csi.github.io/charts/ --force-update >/dev/null
helm repo update democratic-csi >/dev/null
helm upgrade --install "${RELEASE}" democratic-csi/democratic-csi \
  --version "${CHART_VERSION}" \
  --namespace "${NAMESPACE}" \
  --values "${VALUES}" \
  --wait \
  --timeout 5m

printf '🔎 validating CSI objects\n'
kubectl get csidriver org.democratic-csi.nabla.truenas-nfs >/dev/null
kubectl get storageclass truenas-nfs >/dev/null
kubectl get storageclass truenas-nfs-smoke >/dev/null
kubectl wait --namespace "${NAMESPACE}" \
  --for=condition=Ready pod \
  --selector "app.kubernetes.io/instance=${RELEASE}" \
  --timeout=120s >/dev/null

printf '✅ democratic-csi NFS installed: chart=%s, StorageClasses=truenas-nfs/truenas-nfs-smoke\n' \
  "${CHART_VERSION}"
