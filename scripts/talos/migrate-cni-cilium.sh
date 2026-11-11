#!/usr/bin/env bash
# Move the Talos cluster from flannel to Cilium so NetworkPolicy is enforced.
# --plan (default) changes nothing. --apply also needs NABLA_CILIUM_APPLY_APPROVED=yes:
# etcd snapshot, Talos patch (cni: none), flannel removal, Cilium install, then one
# node reboot at a time to drop flannel's leftover interfaces and rules.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
# shellcheck source=scripts/talos/lib/client-config.sh
source "${ROOT}/scripts/talos/lib/client-config.sh"
nabla_resolve_talos_client_config "${ROOT}"
# shellcheck source=../lib/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../lib/common.sh"

MODE="${1:---plan}"
PATCH="${ROOT}/config/talos/patches/cni-none.yaml"
VALUES="${ROOT}/kubernetes/cilium/values.yaml"
CHART_VERSION="$(<"${ROOT}/kubernetes/cilium/VERSION")"
TALOSCTL="${TALOSCTL:-talosctl}"
SNAPSHOT_DIR="${NABLA_TALOS_STATE_DIR:-${HOME}/.local/state/nabla/talos}"

case "${MODE}" in
  --plan | --apply) ;;
  *) fail "usage: bash scripts/talos/migrate-cni-cilium.sh [--plan|--apply]" ;;
esac
[[ "${MODE}" == --plan || "${NABLA_CILIUM_APPLY_APPROVED:-}" == yes ]] ||
  fail "--apply also requires NABLA_CILIUM_APPLY_APPROVED=yes (the whole cluster network restarts)"
for command in "${TALOSCTL}" kubectl helm jq; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

nodes() {
  kubectl get nodes -o json |
    jq -r '.items[] | [(.metadata.labels["node-role.kubernetes.io/control-plane"] != null), (.status.addresses[] | select(.type == "InternalIP") | .address)] | @tsv' |
    sort -r | cut -f2
}
mapfile -t NODE_IPS < <(nodes)
((${#NODE_IPS[@]} > 0)) || fail "no Kubernetes node found"
CONTROL_PLANE="${NODE_IPS[0]}"

flannel_present=false
kubectl -n kube-system get daemonset kube-flannel >/dev/null 2>&1 && flannel_present=true
cilium_release="$(helm -n kube-system list -f '^cilium$' -o json | jq -r '.[0].chart // "absent"')"
printf 'Nodes (control plane first): %s\n' "${NODE_IPS[*]}"
printf 'flannel DaemonSet: %s ; Cilium release: %s ; target chart: cilium-%s\n' \
  "${flannel_present}" "${cilium_release}" "${CHART_VERSION}"

if [[ "${MODE}" == --plan ]]; then
  printf 'Plan: snapshot etcd; patch %s on every node; delete kube-flannel; helm install cilium %s; reboot nodes one by one.\n' \
    "${PATCH#"${ROOT}/"}" "${CHART_VERSION}"
  printf 'Apply: NABLA_CILIUM_APPLY_APPROVED=yes bash %s --apply\n' "${0}"
  exit 0
fi

mkdir -p "${SNAPSHOT_DIR}"
chmod 700 "${SNAPSHOT_DIR}"
snapshot="${SNAPSHOT_DIR}/etcd-$(date -u +%Y%m%dT%H%M%SZ)-before-cilium.snapshot"
"${TALOSCTL}" -n "${CONTROL_PLANE}" etcd snapshot "${snapshot}" >/dev/null
chmod 600 "${snapshot}"
printf '✅ etcd snapshot: %s\n' "${snapshot}"

for ip in "${NODE_IPS[@]}"; do
  "${TALOSCTL}" -n "${ip}" patch machineconfig --patch "@${PATCH}" --mode no-reboot >/dev/null
  printf '✅ %s: cni none\n' "${ip}"
done

kubectl -n kube-system delete daemonset/kube-flannel configmap/kube-flannel-cfg serviceaccount/flannel --ignore-not-found
kubectl delete clusterrolebinding/flannel clusterrole/flannel --ignore-not-found

helm repo add cilium https://helm.cilium.io >/dev/null 2>&1 || true
helm repo update cilium >/dev/null
helm upgrade --install cilium cilium/cilium --version "${CHART_VERSION}" \
  --namespace kube-system --values "${VALUES}" --wait --timeout 10m
printf '✅ Cilium %s installed\n' "${CHART_VERSION}"

for ip in "${NODE_IPS[@]}"; do
  "${TALOSCTL}" -n "${ip}" reboot --wait
  node="$(kubectl get nodes -o json | jq -r --arg ip "${ip}" '.items[] | select(any(.status.addresses[]; .address == $ip)) | .metadata.name')"
  kubectl wait --for=condition=Ready "node/${node}" --timeout=10m
  printf '✅ %s (%s) rebooted and Ready\n' "${node}" "${ip}"
done

kubectl -n kube-system rollout status daemonset/cilium --timeout=10m
printf '✅ Cilium running on every node. Next: bash scripts/talos/smoke-networkpolicy-enforcement.sh\n'
